from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, send, emit
from pymongo import MongoClient
import json
import uuid

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading', logger=True, engineio_logger=True, broadcast=True)

MENU_COLLECTION = 'menu'
ORDER_COLLECTION = 'orders'

# MongoDB connection
client = MongoClient('mongodb+srv://subham:kandari@cluster0.g0fjbkk.mongodb.net/?retryWrites=true&w=majority')
db = client['foodhub']

# Counter variable to keep track of the last generated menu ID
menu_id_counter = 5

# Load menu data from MongoDB
def load_menu_data():
    menu_collection = db[MENU_COLLECTION]
    menu_data = menu_collection.find_one({})
    if menu_data:
        return menu_data.get('menu', {})
    return {}

# Save menu data to MongoDB
def save_menu_data(menu_data):
    menu_collection = db[MENU_COLLECTION]
    menu_collection.update_one({}, {'$set': {'menu': menu_data}}, upsert=True)

# Load order data from MongoDB
def load_order_data():
    order_collection = db[ORDER_COLLECTION]
    order_data = order_collection.find_one({})
    if order_data:
        return order_data.get('orders', {})
    return {}

# Save order data to MongoDB
def save_order_data(order_data):
    order_collection = db[ORDER_COLLECTION]
    order_collection.update_one({}, {'$set': {'orders': order_data}}, upsert=True)

# Generate a unique order ID
def generate_order_id(order_data):
    if order_data:
        order_ids = [order['order_id'] for order in order_data.values()]
        max_order_id = max(order_ids)
        return max_order_id + 1
    else:
        return 1

@app.route('/menu', methods=['GET'])
def get_menu():
    menu = load_menu_data()
    return jsonify(menu)

@app.route('/add_dish', methods=['POST'])
def add_dish():
    dish = request.get_json()
    menu = load_menu_data()

    dish_name = dish.get('dish_name')
    price = dish.get('price')
    availability = dish.get('availability', False)

    if dish_name is None or price is None:
        return jsonify({'message': 'Dish name and price are required!'})

    # Generate a random menu ID using a combination of uuid and the counter
    menu_id = str(uuid.uuid4())

    menu[menu_id] = {
        'dish_id': menu_id,
        'dish_name': dish_name,
        'price': price,
        'availability': availability,
        'rating': [],
        'reviews': []
    }

    save_menu_data(menu)

    return jsonify({'message': 'Dish added successfully!', 'dish': menu[menu_id]})

@app.route('/remove_dish/<dish_id>', methods=['DELETE'])
def remove_dish(dish_id):
    menu = load_menu_data()

    if dish_id not in menu:
        return jsonify({'message': 'Invalid dish ID!'})

    # Remove the dish from the menu
    del menu[dish_id]

    # Save the updated menu data
    save_menu_data(menu)

    return jsonify({'message': 'Dish removed successfully!'})

@app.route('/new_order', methods=['POST'])
def new_order():
    order = request.get_json()
    menu = load_menu_data()
    order_data = load_order_data()
    order_id = generate_order_id(order_data)
    
    dish_ids = order.get('dish_ids', [])
    for dish_id in dish_ids:
        dish = menu.get(dish_id)
        if not dish or not dish.get('availability'):
            return jsonify({'message': 'Invalid dish ID or dish not available!'})

    order_data[order_id] = {
        'order_id': order_id,
        'customer_name': order.get('customer_name'),
        'dish_ids': order.get('dish_ids'),
        'quantity': order.get('quantity'),
        'status': 'received',
        'rating': [],
        'reviews': []
    }
    
    # Convert order_data to a JSON string
    order_data_json = json.dumps(order_data)
    
    # Store the order data in MongoDB
    db.orders.insert_one(json.loads(order_data_json))
    
    # Send a socket event to all connected clients with the updated order status
    socketio.emit('order_status_updated', {'order_id': order_id, 'status': 'received'}, namespace='/')
    
    return jsonify({'message': 'Order placed successfully!', 'order_id': order_id})


@app.route('/update_order_status/<int:order_id>', methods=['PATCH'])
def update_order_status(order_id):
    order_data = load_order_data()

    if order_id not in order_data:
        return jsonify({'message': 'Invalid order ID!'})

    new_status = request.json.get('status')
    if not new_status:
        return jsonify({'message': 'Invalid status!'})

    order_data[order_id]['status'] = new_status
    save_order_data(order_data)

    # Send a socket event to all connected clients with the updated order status
    socketio.emit('order_status_updated', {'order_id': order_id, 'status': new_status})

    return jsonify({'message': 'Order status updated successfully!'})



@app.route('/review_orders', methods=['GET'])
def review_orders():
    order_data = load_order_data()
    return jsonify(order_data)

@app.route('/update_availability/<string:dish_id>', methods=['PATCH'])
def update_availability(dish_id):
    availability = request.json.get('availability')
    menu = load_menu_data()

    if dish_id not in menu:
        return jsonify({'message': 'Invalid dish ID!'})

    menu[dish_id]['availability'] = availability
    save_menu_data(menu)

    return jsonify({'message': 'Availability updated successfully!', 'dish': menu[dish_id]})

@app.route('/update_rating_review/<dish_id>', methods=['PATCH'])
def update_rating_review(dish_id):
    menu = load_menu_data()

    if dish_id not in menu:
        return jsonify({'message': 'Invalid dish ID!'})

    new_rating = request.json.get('rating')
    new_review = request.json.get('reviews')

    if new_rating is None or new_review is None:
        return jsonify({'message': 'Invalid rating or review!'})

    dish = menu[dish_id]
    dish['rating'].append(new_rating)
    dish['reviews'].append(new_review)
    save_menu_data(menu)

    return jsonify({'message': 'Rating and review updated successfully!'})


@socketio.on('connect', namespace='/')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect', namespace='/')
def handle_disconnect():
    print('Client disconnected')

if __name__ == '__main__':
    socketio.run(app, debug=True)
