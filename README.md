# Savannah

Join the beta testing program at [SavannahHQ.com](https://savannahhq.com)

![Community Dashboard](./docs/screenshots/Dashboard.png)

## Create a Development environment

### Using a Virtual Environment

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

### Using Docker

There is now a `Dockerfile` and `docker-compose.yml` in the repo. Use at your discretion.

By default they use Sqlite, but can be configured to use Postgres or Mysql/MariaDB for testing.

#### Create local environment & settings files

```bash
cp .env.template  .env
cp savannah/settings.py local_settings.py
```


#### Build and launch

```bash
docker-compose up --build
```

This will start the savannah app container, and (optionally) a database container. The database initialization is done on first launch.

Next, create an admin account, for which you'll need a username, email address, and password.

```text
docker exec -it savannah-app-1 python manage.py createsuperuser
Username (leave blank to use 'root'):
Email address:
Password:
Password (again):
``` 

If you set that up correctly, you'll see:

```
Superuser created successfully.
```

#### Restart

Stoping the docker container.

```bash
docker stop $(docker ps -qa -f name=savannah_app)
```

Starting the container again.

```bash
docker start savannah_app_1
```

## Setting up Savannah

**WARNING** Savannah is still in very early development and still has a lot of usability rough edges and missing functionality.

### Login

To log in to Savannah go to http://localhost:8000/login and log in.

You'll be presented with "You have no communities" and "Savannah is currently in a open-beta program. You can get free early-access to Savannah to help us test it and provide feedback while we build it.".

This is followed by a "Become a Beta Tester" button. Do not press that.

### Create community

Once logged in you will need to create a new community.

1. Visit the Django admin page at (http://localhost:8000/admin)
2. Find the `COMMUNITY RESOURCE MANAGER` section
3. Locate the `Communities` record and click `+`

Alternatively go directly to http://localhost:8000/admin/corm/community/add/

4. Fill in the following fields as a minimum, leave the rest as defaults, then click `Save` at the bottom.
  - Community Name: My Awesome Community
  - Owner: admin
  - Status: Active

You should see a green banner 'The Community “My Awesome Community” was added successfully.'

This will create community number 1. That number is used in subsequent URLs.

### Visit dashboard

You can now view the Savannah dashboard at http://localhost:8000/dashboard/1/

### Create sources

Savannah can import data from Slack, Github, Discourse and RSS feeds. To import, create a `Source` from the `Sources` page.

Note: Accessing some third party services will require a functioning callback url. 

### Running importers

Once you've created your `Source` you can run the importers with:

```
./env/bin/python manage.py import (slack|github|discourse|rss)
```

Note: When using docker, change the documented commands for importing & tagging data to launch via docker. For example:

```
docker exec -it savannah_app_1 python manage.py import (slack|github|discourse|rss)
```

### Tagging data

You can create `Tags` for your members and conversations from the Django admin interface. If you specify keywords for your tag, all imported conversations will be checked for those keywords and, if found, that `Tag` will be automatically applied to them.

Some useful tags to consider are `thankful` with keywords `thanks, thank you`, and `greeting` with keywords `welcome, hello, hi`.

To auto-tag conversations & contributions, run:
```
./env/bin/python manage.py tag_conversations
./env/bin/python manage.py tag_contributions
```

