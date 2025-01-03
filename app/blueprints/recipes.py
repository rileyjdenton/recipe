from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from app.db_connect import get_db
from werkzeug.utils import secure_filename
import os
import requests

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

recipes = Blueprint('recipes', __name__)

@recipes.route('/recipes')
def list_recipes():
    """Display a list of all recipes with favorite status and additional details."""
    connection = get_db()
    user_id = session.get('user_id')  # Get the logged-in user's ID, if available

    query = """
        SELECT recipes.id, recipes.title, recipes.description, recipes.image_path, 
               recipes.meal_type, recipes.category, users.username,
               EXISTS(
                   SELECT 1 FROM favorites 
                   WHERE favorites.recipe_id = recipes.id AND favorites.user_id = %s
               ) AS is_favorite
        FROM recipes
        JOIN users ON recipes.user_id = users.id
    """
    with connection.cursor() as cursor:
        cursor.execute(query, (user_id,))
        recipes = cursor.fetchall()

    return render_template('recipes/list.html', recipes=recipes)

# Function to ensure all ingredients have a default quantity and unit
def format_ingredients(ingredients):
    formatted = []
    for ingredient in ingredients:
        ingredient = ingredient.strip()
        # If no quantity is specified, default to "1 unit"
        if not any(char.isdigit() for char in ingredient):
            ingredient = f"1 unit {ingredient}"
        formatted.append(ingredient)
    return formatted

@recipes.route('/recipes/<int:recipe_id>')
def view_recipe(recipe_id):
    connection = get_db()

    # Fetch the recipe details
    try:
        recipe_query = """
            SELECT recipes.*, users.username
            FROM recipes
            JOIN users ON recipes.user_id = users.id
            WHERE recipes.id = %s
        """
        with connection.cursor() as cursor:
            cursor.execute(recipe_query, (recipe_id,))
            recipe = cursor.fetchone()
        print("Recipe Details:", recipe)
    except Exception as e:
        print(f"Error fetching recipe details: {e}")
        flash("An error occurred while fetching the recipe.", "danger")
        return redirect(url_for('recipes.list_recipes'))

    if not recipe:
        flash("Recipe not found.", "danger")
        return redirect(url_for('recipes.list_recipes'))

    # Check if nutritional data exists for the recipe
    try:
        nutrition_query = """
            SELECT calories, protein, carbohydrates, fat
            FROM recipe_nutrition
            WHERE recipe_id = %s
        """
        with connection.cursor() as cursor:
            cursor.execute(nutrition_query, (recipe_id,))
            nutrition_data = cursor.fetchone()
        print("Nutrition Data from DB:", nutrition_data)
    except Exception as e:
        print(f"Error fetching nutritional data: {e}")
        nutrition_data = None

    # Edamam API configuration
    APP_ID = 'fee31b76'  # Replace with your app ID
    APP_KEY = '9e2335761d271c35e04b500915aa60ea'  # Replace with your app key
    API_URL = 'https://api.edamam.com/api/nutrition-details'

    # Fetch from API if not in DB
    if not nutrition_data:
        print(f"Nutritional data not found for recipe {recipe_id}. Fetching from API...")
        try:
            formatted_ingredients = [i.strip() for i in recipe['ingredients'].split(',')]
            print("Formatted Ingredients:", formatted_ingredients)

            # Fetch data from Edamam API
            payload = {
                "title": recipe['title'],
                "ingr": formatted_ingredients
            }
            response = requests.post(
                f'{API_URL}?app_id={APP_ID}&app_key={APP_KEY}',
                json=payload
            )

            # Debugging logs
            print("API Status Code:", response.status_code)
            print("API Response:", response.text)

            if response.status_code == 200:
                api_data = response.json()
                nutrition_data = {
                    'calories': api_data.get('calories'),
                    'protein': api_data['totalNutrients'].get('PROCNT', {}).get('quantity', 0),
                    'carbohydrates': api_data['totalNutrients'].get('CHOCDF', {}).get('quantity', 0),
                    'fat': api_data['totalNutrients'].get('FAT', {}).get('quantity', 0),
                }
                save_nutrition_data(recipe_id, nutrition_data)
            else:
                print(f"API Error {response.status_code}: {response.text}")
                flash("Failed to fetch nutritional information from the API.", "warning")
                nutrition_data = None
        except Exception as e:
            print(f"Error fetching or saving nutritional data: {e}")
            flash("An error occurred while fetching nutritional information.", "danger")
            nutrition_data = None

    return render_template('recipes/view.html', recipe=recipe, nutrition_data=nutrition_data)

def save_nutrition_data(recipe_id, nutrition_data):
    print("Saving Nutrition Data:", nutrition_data)

    """Save nutritional data into the database."""
    connection = get_db()
    query = """
        INSERT INTO recipe_nutrition (recipe_id, calories, protein, carbohydrates, fat)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            calories = VALUES(calories),
            protein = VALUES(protein),
            carbohydrates = VALUES(carbohydrates),
            fat = VALUES(fat),
            updated_at = CURRENT_TIMESTAMP
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (
                recipe_id,
                nutrition_data.get('calories'),
                nutrition_data.get('protein'),
                nutrition_data.get('carbohydrates'),
                nutrition_data.get('fat')
            ))
        connection.commit()
    except Exception as e:
        print(f"Error saving nutritional data: {e}")
        connection.rollback()


@recipes.route('/recipes/add', methods=['GET', 'POST'])
def add_recipe():
    if 'user_id' not in session:
        flash("You must be logged in to add a recipe.", "danger")
        return redirect(url_for('users.login'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        ingredients = request.form['ingredients']
        instructions = request.form['instructions']
        meal_type = request.form['meal_type']
        category = request.form['category']
        user_id = session['user_id']

        # Handle image upload
        image_file = request.files.get('image')
        image_path = None

        if image_file and allowed_file(image_file.filename):
            filename = secure_filename(image_file.filename)
            uploads_folder = os.path.join(current_app.root_path, 'static/uploads')

            # Ensure the uploads folder exists
            os.makedirs(uploads_folder, exist_ok=True)

            # Save the file
            image_path = os.path.join(uploads_folder, filename)
            image_file.save(image_path)

            # Update image path for database (relative to static folder)
            image_path = f'static/uploads/{filename}'

        # Insert recipe into database
        connection = get_db()
        query = """
            INSERT INTO recipes (user_id, title, description, ingredients, instructions, image_path, meal_type, category) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        with connection.cursor() as cursor:
            cursor.execute(query,
                           (user_id, title, description, ingredients, instructions, image_path, meal_type, category))
        connection.commit()

        flash("Recipe added successfully!", "success")
        return redirect(url_for('recipes.list_recipes'))

    return render_template('recipes/add.html')

@recipes.route('/recipes/edit/<int:recipe_id>', methods=['GET', 'POST'])
def edit_recipe(recipe_id):
    """Edit an existing recipe."""
    if 'user_id' not in session:
        flash("You must be logged in to edit a recipe.", "danger")
        return redirect(url_for('users.login'))

    connection = get_db()
    query = """
        SELECT recipes.*, users.username
        FROM recipes
        JOIN users ON recipes.user_id = users.id
        WHERE recipes.id = %s
    """
    with connection.cursor() as cursor:
        cursor.execute(query, (recipe_id,))
        recipe = cursor.fetchone()

    if not recipe:
        flash("Recipe not found.", "danger")
        return redirect(url_for('recipes.list_recipes'))

    # Check if the logged-in user is the owner of the recipe
    if session['user_id'] != recipe['user_id']:
        flash("You are not authorized to edit this recipe.", "danger")
        return redirect(url_for('recipes.list_recipes'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        ingredients = request.form['ingredients']
        instructions = request.form['instructions']
        meal_type = request.form['meal_type']
        category = request.form['category']
        image_file = request.files.get('image')

        # Handle image upload
        image_path = recipe['image_path']  # Default to current image
        if image_file and allowed_file(image_file.filename):
            filename = secure_filename(image_file.filename)
            image_path = os.path.join('static/uploads', filename).replace("\\", "/")
            image_file.save(os.path.join(current_app.root_path, image_path))

        # Update recipe in the database
        update_query = """
            UPDATE recipes
            SET title = %s, description = %s, ingredients = %s, instructions = %s, image_path = %s, meal_type = %s, category = %s
            WHERE id = %s
        """
        with connection.cursor() as cursor:
            cursor.execute(update_query, (title, description, ingredients, instructions, image_path, meal_type, category, recipe_id))
        connection.commit()

        flash("Recipe updated successfully!", "success")
        return redirect(url_for('recipes.view_recipe', recipe_id=recipe_id))

    return render_template('recipes/edit.html', recipe=recipe)

@recipes.route('/recipes/delete/<int:recipe_id>', methods=['POST'])
def delete_recipe(recipe_id):
    """Delete an existing recipe."""
    print(f"Attempting to delete recipe ID: {recipe_id}")

    if 'user_id' not in session:
        flash("You must be logged in to delete a recipe.", "danger")
        return redirect(url_for('users.login'))

    connection = get_db()

    # Fetch the recipe to check ownership
    query = "SELECT * FROM recipes WHERE id = %s"
    with connection.cursor() as cursor:
        cursor.execute(query, (recipe_id,))
        recipe = cursor.fetchone()

    if not recipe:
        flash("Recipe not found.", "danger")
        return redirect(url_for('recipes.list_recipes'))

    # Check if the logged-in user is the owner of the recipe
    if session['user_id'] != recipe['user_id']:
        flash("You are not authorized to delete this recipe. Only the recipe's creator can delete it.", "danger")
        return redirect(url_for('recipes.list_recipes'))

    # Delete the recipe
    delete_query = "DELETE FROM recipes WHERE id = %s"
    with connection.cursor() as cursor:
        cursor.execute(delete_query, (recipe_id,))
    connection.commit()

    flash("Recipe deleted successfully!", "success")
    return redirect(url_for('recipes.list_recipes'))

@recipes.route('/recipes/favorite/<int:recipe_id>', methods=['POST'])
def toggle_favorite(recipe_id):
    """Toggle the favorite status of a recipe for the logged-in user."""
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    connection = get_db()
    user_id = session['user_id']

    # Check if the recipe is already favorited
    query = "SELECT * FROM favorites WHERE user_id = %s AND recipe_id = %s"
    with connection.cursor() as cursor:
        cursor.execute(query, (user_id, recipe_id))
        favorite = cursor.fetchone()

    if favorite:
        # Remove from favorites
        query = "DELETE FROM favorites WHERE user_id = %s AND recipe_id = %s"
        with connection.cursor() as cursor:
            cursor.execute(query, (user_id, recipe_id))
        connection.commit()
        return jsonify({"message": "Unfavorited", "is_favorited": False})
    else:
        # Add to favorites
        query = "INSERT INTO favorites (user_id, recipe_id) VALUES (%s, %s)"
        with connection.cursor() as cursor:
            cursor.execute(query, (user_id, recipe_id))
        connection.commit()
        return jsonify({"message": "Favorited", "is_favorited": True})

@recipes.route('/recipes/search')
def search_recipes():
    """Search for recipes based on a query."""
    user_query = request.args.get('query', '').strip()  # User input
    connection = get_db()

    if not user_query:
        flash("Please enter a search term.", "warning")
        return redirect(url_for('recipes.list_recipes'))

    search_query = f"%{user_query}%"
    sql_query = """
        SELECT recipes.id, recipes.title, recipes.description, recipes.image_path,
               recipes.meal_type, recipes.category, users.username
        FROM recipes
        JOIN users ON recipes.user_id = users.id
        WHERE recipes.title LIKE %s OR recipes.description LIKE %s OR recipes.category LIKE %s
    """
    with connection.cursor() as cursor:
        cursor.execute(sql_query, (search_query, search_query, search_query))
        results = cursor.fetchall()

    # Pass the user's query to the template
    return render_template('recipes/search_results.html', query=user_query, results=results)

@recipes.route('/recipes/filter')
def filter_recipes():
    """Filter recipes by meal type and/or username."""
    meal_type = request.args.get('meal_type', '').strip()
    username = request.args.get('username', '').strip()
    connection = get_db()

    # Base query to retrieve recipes
    query = """
        SELECT recipes.id, recipes.title, recipes.description, recipes.image_path,
               recipes.meal_type, recipes.category, users.username
        FROM recipes
        JOIN users ON recipes.user_id = users.id
        WHERE 1=1
    """
    params = []

    # Add meal_type filter if provided
    if meal_type:
        query += " AND recipes.meal_type = %s"
        params.append(meal_type)

    # Add username filter if provided
    if username:
        query += " AND users.username = %s"
        params.append(username)

    # Execute the query with the parameters
    with connection.cursor() as cursor:
        cursor.execute(query, tuple(params))
        recipes = cursor.fetchall()

    return render_template('recipes/list.html', recipes=recipes)
