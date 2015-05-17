from flask import Flask, render_template, request, redirect
from flask import jsonify, url_for, flash, Response
from flask import session as login_session
from flask import make_response
from sqlalchemy import create_engine, asc, desc, func
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Category, Item, User
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import bleach
import random
import string
import httplib2
import json
import requests
import time

app = Flask(__name__)

CLIENT_ID = json.loads(
    open('client_secret.json', 'r').read())['web']['client_id']

APPLICATION_NAME = "Catalog Application"

# Connect to Database and create database session
engine = create_engine('sqlite:///catalog.db')
Base.metadata.bind = engine

# Set up database session
DBSession = sessionmaker(bind=engine)
session = DBSession()

# region: standard endpoints

@app.route('/login')
def showLogin():
    """Displays login page."""

    state = ''.join(
        random.choice(string.ascii_uppercase + string.digits) \
            for x in range(32))
    login_session['state'] = state
    return render_template('login.html', STATE=state)

@app.route('/gconnect', methods=['POST'])
def gconnect():
    """Logs a user into their Google account."""

    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code, now compatible with Python3
    request.get_data()
    code = request.data.decode('utf-8')

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secret.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    # Submit request, parse response - Python3 compatible
    h = httplib2.Http()
    response = h.request(url, 'GET')[1]
    str_response = response.decode('utf-8')
    result = json.loads(str_response)

    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('Current user is already connected.'),
                                 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['email'] = data['email']

    # see if user exists, if it doesn't make a new one
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    return "You have successfully logged in."

@app.route('/gdisconnect')
def gdisconnect():
    """Disconnects a logged-in Google+ user."""

    # Only disconnect a connected user.
    access_token = login_session.get('access_token')
    if access_token is None:
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    if result['status'] == '200':
        # Reset the user's sesson.
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']

        return redirect(url_for('showIndex'))
    else:
        # For whatever reason, the given token was invalid.
        try:
            # try to reset any residual session anyway
            del login_session['access_token']
            del login_session['gplus_id']
            del login_session['username']
            del login_session['email']
            del login_session['user_id']
        except:
            pass
        response = make_response(
            json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response

@app.route('/', defaults={'category_id':None})
@app.route('/categories/<int:category_id>/')
def showIndex(category_id):
    """Displays index page."""

    categories = get_categories()

    latest_items = None
    category_items = None

    # display category items if specified, otherwise latest items
    if category_id == None:
        latest_items = session.query(Item).order_by(desc(
            Item.last_update)).limit(10)
    else:
        category_items = session.query(Item).filter_by(
            category_id=category_id).order_by(asc(func.lower(Item.name))).all()

    return render_template('index.html', categories=categories,
                           latest_items=latest_items,
                           category_items=category_items)

@app.route('/items/<int:item_id>/')
def showItem(item_id):
    """Displays page for specific item."""

    categories = get_categories()
    item = session.query(Item).filter_by(id=item_id).one()
    return render_template('item.html', item=item, categories=categories)

@app.route('/items/add/', methods=['GET', 'POST'])
def addItem():
    """Displays the add item page."""

    if request.method == 'POST':
        # verify the user has logged in
        if 'username' not in login_session:
            return redirect(url_for('showLogin'))

        if request.form.get('add', None) == 'add':
            name = bleach.clean(request.form['name'], 
                                strip=True)

            # verify that cleaned name is not blank
            if not name:
                flash("Name field is required")
                categories = get_categories()
                return render_template('addItem.html',
                                       categories=categories)

            #build the new item
            item = Item()
            item.name = name
            item.description = bleach.clean(request.form['description'],
                                            strip=True)
            item.image_url = bleach.clean(request.form['imageUrl'],
                                          strip=True)
            item.category_id = bleach.clean(request.form['category'],
                                            strip=True)

            item.last_update = get_time()
            item.owner_id = login_session['user_id']
            session.add(item)
            session.commit()

            return redirect(url_for('showItem', item_id=item.id))
        else:
            return redirect(url_for('showIndex'))
    else:
        categories = get_categories()
        return render_template('addItem.html', categories=categories)

@app.route('/items/<int:item_id>/edit', methods=['GET', 'POST'])
def editItem(item_id):
    """Displays the edit item page."""

    # verify the user has logged in
    if 'username' not in login_session:
        return redirect(url_for('showLogin'))

    item = session.query(Item).filter_by(id=item_id).one()

    # verify user owns this item
    if item.owner_id != login_session['user_id']:
        return redirect(url_for('showItem', item_id=item_id))

    # handle request
    if request.method == 'POST':
        if request.form.get('save', None) == 'save':
            name = bleach.clean(request.form['name'], 
                                strip=True)

            # verify that cleaned name is not blank
            if not name:
                flash("Name field is required")
                categories = get_categories()
                return render_template('editItem.html', item=item,
                                       categories=categories)

            # update time
            item.name = name
            item.description = bleach.clean(request.form['description'],
                                            strip=True)
            item.image_url = bleach.clean(request.form['imageUrl'],
                                          strip=True)
            item.category_id = bleach.clean(request.form['category'],
                                            strip=True)
            item.last_update = get_time()

            session.commit()

        return redirect(url_for('showItem', item_id=item_id))
    else:
        categories = get_categories()
        return render_template('editItem.html', item=item,
                               categories=categories)

@app.route('/items/<int:item_id>/delete', methods=['GET', 'POST'])
def deleteItem(item_id):
    """Displays the delete item page."""

    # verify the user has logged in
    if 'username' not in login_session:
        return redirect(url_for('showLogin'))

    item = session.query(Item).filter_by(id=item_id).one()

    # verify user owns this item
    if item.owner_id != login_session['user_id']:
        return redirect(url_for('showItem', item_id=item_id))

    # handle request
    if request.method == 'POST':
        if request.form.get('delete', None) == 'delete':
            session.delete(item)
            session.commit()
            return redirect(url_for('showIndex', 
                                    category_id=item.category_id))
        else:
            return redirect(url_for('showItem', item_id=item_id))
    else:
        categories = get_categories()
        return render_template('deleteItem.html', item=item,
                               categories=categories)

# region: JSON endpoints

@app.route('/json/')
def getAllItemsJson():
    """JSON endpoint for all items."""

    items = session.query(Item).order_by(asc(func.lower(Item.name))).all()
    return jsonify(Items=[i.serialize for i in items])

@app.route('/items/<int:item_id>/json/')
def getItemJson(item_id):
    """JSON endpoint for a specific item."""

    item = session.query(Item).filter_by(id=item_id).one()
    return jsonify(item.serialize)

@app.route('/categories/<int:category_id>/json/')
def getCategoryItemsJson(category_id):
    """JSON endpoint for items in specified category."""

    items = session.query(Item).filter_by(category_id=category_id) \
        .order_by(asc(func.lower(Item.name))).all()
    return jsonify(Items=[i.serialize for i in items])

# region: helper methods

def get_categories():
    """Gets all categories from database."""

    return session.query(Category).order_by(asc(Category.name)).all()

def get_time():
    """Returns the current time in milliseconds."""

    return int(round(time.time() * 1000))

def createUser(login_session):
    """Creates a new user in the database."""

    newUser = User(email=login_session['email'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id

def getUser(user_id):
    """Gets user with supplied user id from the database."""

    user = session.query(User).filter_by(id=user_id).one()
    return user

def getUserID(email):
    """Gets the ID of user with supplied email."""

    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None

if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=8000)