python3 -m venv .
. bin/activate
pip install -r requirements.txt
pip freeze > requirements.txt

cd lib/python3.8/site-packages
zip -r ../../../bundels.zip .
cd ../../..
zip -g bundels.zip lambda_function.py