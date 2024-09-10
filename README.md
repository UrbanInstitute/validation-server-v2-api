# Validation Server (Version 2.0) - API

This repository contains the Django REST API for the Urban Institute's [Safe Data Technologies](https://www.urban.org/projects/safe-data-technologies) Validation Server Version 2.0 prototype. The API is integrated into the AJAX architecture, which connects the frontend of the system to the backend engine.

## Quick Links
- [Technical White Paper](https://www.urban.org/research/publication/privacy-preserving-validation-server-version-2) 
- [Staging URL](https://sdt-validation-server.urban.org) 
- [Swagger Interface](https://sdt-validation-server.urban.org/api/docs)

## Related Repositories
- [validation-server-v2-backend](https://github.com/UrbanInstitute/validation-server-v2-backend): Backend for the validation server version 2.0 prototype
- [validation-server-v2-frontend](https://github.com/UrbanInstitute/validation-server-v2-frontend): Frontend for the validation server version 2.0 prototype
- [validation-server-v2-infrastructure](https://github.com/UrbanInstitute/validation-server-v2-infrastructure): CloudFormation stack for the API and frontend infrastructure of the validation server version 2.0 prototype

## Build and Deployment Instructions

**Note**: CI/CD is removed from the public version of the code in this repository. The instructions below describe how CI/CD is managed in the codebase under active development. Please contact us if you are interested in setting up CI/CD for your own deployment and have questions. 

The template uses two different docker-compose files:

#### docker-compose.yml
This docker-compose file is used for local testing only.

To test your code along with the database locally: `docker-compose up`

- Local URL for testing the app: http://127.0.0.1:8000 (http://0.0.0.0:8000 on Mac)
- Local URL for testing the sample API endpoints: http://127.0.0.1:8000/api/v1/samples (http://0.0.0.0:8000/api/v1/samples on Mac)
- Local URL: for testing the sample API endpoint with `drf-spectacular` and Swagger: http://localhost/api/v1/docs/ (http://0.0.0.0/api/v1/docs)

#### docker-compose-deploy.yml
This docker-compose file is used for deployment (to staging and production) using NGINX. It can also be tested locally, which can be seen as a sandbox or pre-staging.

To test the docker-compose-deploy.yml file: `docker-compose -f docker-compose-deploy.yml up`

- Local URL for testing the app via NGINX: http://localhost
- Local URL for testing the sample API endpoints: http://localhost/api/v1/samples

#### .env file 
For local development, create a `.env` file in the root directory of the project with the following variables:

```bash
DEBUG
MYSQL_DATABASE
MYSQL_USER
MYSQL_PASSWORD
MYSQL_ROOT_PASSWORD
DJANGO_SECRET_KEY
ALLOWED_HOSTS
MYSQL_HOST
AWS_STORAGE_BUCKET_NAME
AWS_S3_REGION_NAME
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
DJANGO_SUPERUSER_PASSWORD
DJANGO_SUPERUSER_USERNAME
DJANGO_SUPERUSER_EMAIL
AWS_SANITIZER_LAMBDA
AWS_STEPFUNCTION
```

#### Build and run the container
To build the container for the first time with the local docker-compose file, run the following command:

```bash
docker-compose up --build
```

To build and run the docker-compose for deployment, run the following command:

```bash
docker-compose -f docker-compose-deploy.yml up --build
```

#### Backup SQL data
To export your SQL data to a local file, run this command:

```bash
docker exec -it db sh ./scripts/export_mysql_backup.sh
```
You'll be prompted for the MySQL password for the dev user in the console.

#### NGINX
The local testing with docker-compose.yml does not use NGINX. The static files and other URLS served by UWSGI are implemented with Django.

#### Create user groups if starting DB from scratch
To create user groups, run the following command: 
```bash
docker-compose run --rm app sh -c "python manage.py createusergroups"
```

#### Running and testing locally
To build the images, run the following command: 
```bash
docker-compose build
```

Start up the development server and containers with the following command:
```bash
docker-compose up
```

- Open 127.0.0.1:8000/api/admin to get to the admin panel
- Open 127.0.0.1:8000/api/docs to get to the SwaggerUI 
- Open 127.0.0.1:8000/api/schemas to get the API schemas

Run unit tests with the following command: 
```bash
docker-compose run --rm app sh -c "python manage.py test"
```
To run a specific test case, e.g. the `PublicUserApiTests`, use the following command:
```bash
docker-compose run --rm app sh -c "python manage.py test <app>.tests.<module>.<class>"
docker-compose run --rm app sh -c "python manage.py test users.tests.test_user_api.PublicUserApiTests"
```
To run a specific test method within a test case, e.g. the `PublicUserApiTests`, use the following command: 
```bash
docker-compose run --rm app sh -c "python manage.py test <app>.tests.<module>.<class>.<method>"
docker-compose run --rm app sh -c "python manage.py test users.tests.test_user_api.PublicUserApiTests.test_create_token_for_user"
```

If you get the error message "Access denied for user 'dev'@'%' to database 'test_db'", then the DB user "dev" does not have permission to create a database. Add the permission:
```bash
docker-compose run --rm db sh -c "mysql -uroot -p"
```
Enter root password.
```bash
GRANT ALL ON *.* TO 'dev'@'%';
```
If you get the message "Got an error creating the test database: database 'test_db' already exists.", enter "yes" and continue.

See all implemented URLs and patterns:
```bash
docker-compose  run --rm app sh -c "python manage.py show_urls"
```

## Development Process
This API is developed using test-driven development practices. Please follow this pattern when adding new functionality:
<ol>
  <li>Create one or more tests for the new feature you are about to implement. The tests should be created in the folder of the corresponding application. I.e. if you implement a feature for the Job API, add the test code to the test folder in the job app folder.</li>
  <li>Check the implementation of your test case by running</li>
      
      docker-compose run --rm app sh -c "python manage.py test"
      
  <li>Make sure the test case fails due to the feature not being implemented yet. Fix any other errors (syntax, spelling).</li>
  <li>Implement the feature.</li>
  <li>Check if tests are passing by running</li>
    
      docker-compose run --rm app sh -c "python manage.py test"
</ol>

## Contact
This work is developed by the Urban Institute. For questions, reach out to: validationserver@urban.org. 
