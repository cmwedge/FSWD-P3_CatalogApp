Catalog Application: README
---------------------------
Prerequisite Libraries:
* sqlalchemy
* bleach
* oauth2client
* requests
* httplib2
* Flask

Install/Start:
1. Copy files to desired location.
2. Execute: python database_setup.py
3. Execute: python populate_database.py
4. Execute: python application.py

Use:
Navigate to http://localhost:8000 for standard web page experience. Alternatively, the following API endpoints are exposed to display item information in JSON format:
* All items: http://localhost:8000/json
* Items for specified category: http://localhost:8000/categories/<int:category_id>/json
* Specific item: http://localhost:8000/items/<int:item_id>/json

Notes:
* Application only allows logins from Google+ accounts.
* Much of the user handling logic in application.py is based on class exercise code.
