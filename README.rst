AHGL - After Hours Gaming League
================================

This is the source for http://afterhoursgaming.tv/

Platform
--------
This site is built upon the following basic platform:

* python
* django
* postgres - relational database
* redis - for caching
* celery - for task queue
* south - for database migrations

Setup
-----
To setup an environment to test locally, you should first install `Python (2.7)
<http://python.org/>`_, `pip <http://pypi.python.org/pypi/pip>`_, and
`virtualenv <http://pypi.python.org/pypi/virtualenv>`_ as well as `PostgreSQL
<http://postgresql.com>`_ (although you can use SQLite if necessary).

Pip is the python package management tool that will allow you to install all the
other python libraries that are used quite easily. Virtualenv allows you to have
segregated python installs that have different libraries.

Create a virtual env::

    $ virtualenv --distribute ENV

Start that environment::

    $ ENV/Scripts/activate
	
Now install the python libraries using pip::

    $ pip install --requirement=ahgl/requirements/project.txt
	
You'll want to create a local_settings.py file to specify your settings based on
your local setup::

    $ cp ahgl/local_settings.py{.dist,}

Then edit it to verify/change any of the options.

If all of that worked, you should be able to initialize the database by running
from the ahgl folder::

    $ ./manage.py syncdb
    $ ./manage.py migrate
	
Now that everything is setup, you can run the local service::

    $ ./manage.py runserver
	
Now visit localhost and you should see a web page appear!
