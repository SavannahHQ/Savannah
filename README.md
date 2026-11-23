# Savannah

Join the beta testing program at [SavannahHQ.com](https://savannahhq.com)

![Community Dashboard](./docs/screenshots/Dashboard.png)

## Create a Development environment

To get started running Savannah in your development environment, first create a Python virtualenv:

```
virtualenv --python=python3 ./env
```

Then install the requirements:

```
./env/bin/pip install -r requirements.txt
```

Next you'll need to initialize the database and create an admin account:

```
./env/bin/python manage.py migrate
./env/bin/python manage.py createsuperuser
```

This will create an SQLite database at ./db.sqlite in your local directory.

Finally run the development server:

```
./env/bin/python manage.py runserver
```

## Setting up Savannah

**WARNING** Savannah is still in very early development and still has a lot of usability rough edges and missing functionality.

To log in to Savannah go to http://localhost:8000/login and log in.

Once logged in you will need to go to the Django admin (http://localhost:8000/admin) and create a new `Community` record.

You can now view the Savannah dashboard at http://localhost:8000/dashboard/1/

Savannah can import data from Slack, Github, Discourse and RSS feeds. To import, create a `Source` from the `Sources` page.


### Running importers

Once you've created your `Source` you can run the importers with

```
./env/bin/python manage.py import (slack|github|discourse|rss)
```

### Tagging data

You can create `Tags` for your members and conversations from the Django admin interface. If you specify keywords for your tag, all imported conversations will be checked for those keywords and, if found, that `Tag` will be automatically applied to them.

Some useful tags to consider are `thankful` with keywords `thanks, thank you`, and `greeting` with keywords `welcome, hello, hi`.

To auto-tag conversations & contributions, run:
```
./env/bin/python manage.py tag_conversations
./env/bin/python manage.py tag_contributions
```

## Running the tests

The tests need Python 3.8 and a PostgreSQL server, because they build their database by running every migration the way a new PostgreSQL installation does.

Install the test tools next to the application requirements:

```
./env/bin/pip install -r requirements.txt -r requirements-dev.txt
```

Tell the tests where PostgreSQL is and run them:

```
export DATABASE_HOST=localhost DATABASE_NAME=savannah DATABASE_USER=savannah DATABASE_PASSWORD=savannah
./env/bin/pytest
```

`DATABASE_PORT` defaults to 5432. The tests never touch `DATABASE_NAME` itself: they create and drop a separate `test_<DATABASE_NAME>` database (or the one named by `TEST_DATABASE_NAME`), so the user needs permission to create databases. The settings they run with are in `savannah/test_settings.py`.
