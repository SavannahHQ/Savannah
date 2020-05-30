# Savannah

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

To log in to Savannah you currently have to use the Django admin login system. If running in a local development environment from the steps above, go to http://localhost:8000/admin/ and log in.

Once logged in you will be in the Django admin, where you can look at the database models and content that you have. Here you'll need to do some initial setup:

1. Create a new `Community` for your initial community. You can have more than one, but you need at least one.
2. Create a new `Member` for yourself, be use to set your `User` that you created with `manage.py createsuperuser` earlier

You can now view the Savannah dashboard at http://localhost:8000/dashboard/1/

## Importing data

Savannah currently provides importers for Slack and Github. To import data from Slack or Github:

1. Create a new `Source` object, selecting the appropriate `Connector` from the list.
2. Add your OAuth token to the `auth_secret` field
3. Set the `Icon name` to `fab fa-slack` or `fab fa-github` respectively
4. Add a `Last import` date of sometime in the past. Only conversations after that date will be imported.
5. Create a new `Channel` object for each Slack channel or Github repository you want to import data from
   1. For Slack, use the internal slack channel ID for the `origin id` field
   2. For Github, use the URL to your repo for the `origin id` field.

### Running importers

Once you've created your `Source` and `Channel` records for these you can run the importers with

```
./env/bin/python manage.py import (slack|github|discourse)
```

### Tagging data

You can create `Tags` for your members and conversations from the Django admin interface. If you specify keywords for your tag, all imported conversations will be checked for those keywords and, if found, that `Tag` will be automatically applied to them.

Some useful tags to consider are `thankful` with keywords `thanks, thank you`, and `greeting` with keywords `welcome, hello, hi`.

To auto-tag conversations & contributions, run:
```
./env/bin/python manage.py tag_conversations
./env/bin/python manage.py tag_contributions
```
