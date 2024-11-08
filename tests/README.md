# Pytest

Run unit tests with `python -m pytest`. Pytest will automatically detect files, classes, and methods with the Pytest naming convention. 

To see the full output of the tests: `python -m pytest -v`

To run a specific directory: `python -m pytest unittests/`

To run a specific test file: `python -m pytest unittests/test_sensors.py`

To run a specific test: `python -m pytest -k 'test_something'`


# CI/CD

The scripts defined in `.gitlab-ci.yml` are run whenever a new commit is made. These scripts can also be manually run in the CI/CD tab without having to make a commit.

Pytest is invoked through the `.gitlab-ci.yml`. Change the contents of this file to run different pytest commands.


# Virtual Environment

Because these tests are run on a shared Raspberry Pi, please make sure to use a virtual environment(venv) to maintain a clean work environment. Python venv should already be installed on the Pi.

Create a new virtual environment with `virtualenv <replace-with-name>`. This creates a venv file that contains describes the virtual environment.

Activate the environment with `source venv/bin/activate`. This is path specific. Usually called with `source activate.bat` or `source activate.sh`.

Once again, the virtual environment setup is already defined in `.gitlab-cy.yml`.
