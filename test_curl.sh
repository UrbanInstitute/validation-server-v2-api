# cUrl commands for local testing

# Login to API and retrieve token
curl -d '{"email": "<email>", "password": "<password>"}' -H "Content-Type: application/json" -X POST 127.0.0.1:8000/api/users/login/

# Create a new job
curl -F "title=Example title" -F "script=@test.R" -H "Authorization: Token <Token>"  -X POST 127.0.0.1:8000/api/job/jobs/

# Upload a script to existing job
curl -F "script=@test.R" -H "Authorization: Token <Token>" 127.0.0.1:8000/api/job/jobs/<id>/upload-script/

# Update the status of a job (need to be authorized as user in group "engine")
curl -X PATCH -d "{'status': '{'ok': True, 'info': 'Example info', 'errormsg': 'Error message'}'}" -H "Authorization: Token <Token>" 127.0.0.1:8000/api/job/jobs/<id>/
