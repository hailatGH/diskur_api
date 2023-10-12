Welcome to the **MoogtMeda** repository. This file documents the development environment for this project. MoogtMeda is implemented in [Python 3.7.0](https://www.python.org/downloads/release/python-370/).

---

## Getting Started

Jump start your development with these simple steps.

# If you want to run this project using docker

1. Install docker into your system(download and install from [docker doc](https://docs.docker.com/get-docker/))
2. Run the command `docker-compose build` then `docker-compose up`

# If you don't want to run the project in docker you can follow the following steps.

# Installing Python, PIP and Virtualenv

1. Install Python [Python 3.7.0](https://www.python.org/downloads/release/python-370/) or later.
2. Check if pip is already installed with Python via `pip --version`. If not, [install it](https://pip.pypa.io/en/stable/installing/).
3. [Install git](https://git-scm.com/download/) if not already installed (check with `git --version`).
4. Install virtualenv with `pip install virtualenv`.

# Installing Angular

5. Install [Node.js](https://nodejs.org/en/) and npm. (On Linux/Ubuntu, `curl -sL https://deb.nodesource.com/setup_12.x | sudo -E bash -` and `sudo apt-get install -y nodejs`)
6. Install the Angular CLI globally using npm:
   `npm install -g @angular/cli`

# Setting up your workspace

5. Create your own fork of this repository. Then, in your home directory (`cd ~`), clone your forked repository with `git clone https://[your_bit_bucket_username]@bitbucket.org/[your_bit_bucket_username]/moogtmeda.git`.
6. In your repo directory (`cd ~/moogtmeda`), create a new virtualenv with `virtualenv -p python venv`.
7. Activate your new virtualenv with `source venv/bin/activate` (on Mac, Linux) or `source venv/Scripts/activate` (Windows via Git Bash). This should show the `(venv)` prexif on your command line prompt. You can exit the virtualenv with `deactivate`.
8. With `(venv)` activated, install Django and other requirements with `pip install -U -r moogtmeda/requirements.txt`.

# Setting up your database

9. Install PostgreSQL from PostgreSQL Apt Repository:

   a) Add PostgreSQL Repository Import the GPG repository key with the commands:
   `sudo apt-get install wget ca-certificates`

   `wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -`

   b) Then, add the PostgreSQL repository by typing: `` sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt/ `lsb_release -cs`-pgdg main" >> /etc/apt/sources.list.d/pgdg.list'  ``

   c) Then Update the Package List: `sudo apt-get update`

   d) Then Install PostgreSQL: `sudo apt-get install postgresql postgresql-contrib`

10. Create Database:

    a) Enter an interactive Postgres session by typing:
    `sudo -u postgres psql`

    b) `CREATE DATABASE moogter;`

    c) Create User for Database: `CREATE USER moogter_dev_user WITH PASSWORD ‘dev_password‘;`

    d) We set the default encoding to UTF-8, which is expected by Django:
    `ALTER ROLE moogter_dev_user SET client_encoding TO ‘utf8’;`

    e) Set a default transaction isolation scheme to “read commits”:
    `ALTER ROLE moogter_dev_user SET default_transaction_isolation TO ‘read committed’;`

    f) Finally, we set the time zone. By default, our Django project will be set to use UTC:
    `ALTER ROLE moogter_dev_user SET timezone TO ‘UTC’;`

    g) Give our database user access rights to the database that we created:
    `GRANT ALL PRIVILEGES ON DATABASE moogter TO moogter_dev_user;`

    h) Exit the SQL prompt to return to the postgres user shell session:
    `\q`

11. (Optional) Install pgAdmin, which is a GUI database management tool for PostgreSQL using this [link](https://www.pgadmin.org/download/pgadmin-4-apt/).

# Running the MoogtMeda server locally

12. At this point, you're all set to run the server! To do this locally, follow the following steps.

    a) Apply all database migrations.
    `python manage.py migrate`

    b) Compile static contents.
    `python manage.py compilestatic`

    c) Go to the `moogter-web` directory.
    `cd ../moogter-web`

    d) Install all the necessary packages required by the angular project.
    `npm install`

    e) Start the Angular Development server.
    `ng serve`

    f) Run the Django server on a separate terminal window.
    `python manage.py runserver`

    Then open up a browser and go to `http://localhost:4200/`.

# Development workflow

13. The 'master' branch always contains the live version of the server. NEVER develop directly on the matster branch. When you want to make a change, create a new branch while on 'master' with `git branch new-branch-name` and `git checkout new-branch-name`. After you create your commit locally, run `git push origin new-branch-name` to push your changes to bitbucket. Then go on bitbucket and under "Pull requests" click "create a pull request" and select your branch. Once your changes have been reviewed and approved, they will be merged in to 'master'.

---
# moogter_api
