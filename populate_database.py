from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_setup import Category, Item, User, Base
import time
import csv

ITEMS_CSV = "items.csv"
CATEGORIES_CSV = "categories.csv"
USERS_CSV = "users.csv"

def load_categories_from_csv():
    categories = []
    try:
        with open(CATEGORIES_CSV, 'r') as f:
            rdr = csv.reader(f)
            for row in rdr:
                categories.append(Category(name=row[0]))
    except:
        print("A problem occurred reading categories from category file.")
        raise

    return categories

def load_users_from_csv():
    users = []
    try:
        with open(USERS_CSV, 'r') as f:
            rdr = csv.reader(f)
            for row in rdr:
                users.append(User(email=row[0]))
    except:
        print("A problem occurred reading users from users file.")
        raise

    return users

def load_items_from_csv():
    items = []
    try:
        with open(ITEMS_CSV, 'r') as f:
            rdr = csv.reader(f, delimiter='|')
            for row in rdr:
                cur_ms = int(round(time.time() * 1000))
                items.append(Item(name=row[1], description=row[2],
                                  image_url=row[0], last_update=cur_ms))
    except:
        print("A problem occurred reading items from items file.")
        raise

    return items

def populate_database():
    engine = create_engine('sqlite:///catalog.db')
    Base.metadata.bind = engine

    DBSession = sessionmaker(bind=engine)
    session = DBSession()

    items = load_items_from_csv()
    categories = load_categories_from_csv()
    users = load_users_from_csv()
    clen = len(categories)
    ulen = len(users)

    for user in users:
        session.add(user)
        session.commit()

    for category in categories:
        session.add(category)
        session.commit()

    for i in range(len(items)):
        item = items[i]
        item.category = categories[i%clen]
        item.owner = users[i%ulen]
        session.add(item)
        session.commit()

if __name__ == "__main__":
    populate_database()