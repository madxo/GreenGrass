from flask import Flask, render_template_string, request
import nltk
nltk.download('vader_lexicon')
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import sys
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
import json
import random
from pymongo import MongoClient
import logging
import boto3
import os
from datetime import datetime

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

ec2 = boto3.client('ec2', region_name='ap-south-1',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'), aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'))
response = ec2.describe_instances(InstanceIds=[os.environ.get('INSTANCE_ID')])
instance = response['Reservations'][0]['Instances'][0]

#Creating a pymongo client
client = MongoClient(instance.get('PublicIpAddress'), 27017)

#Getting the database instance
database = client['mydb']

#Creating a collection
coll = database['example']

app = Flask(__name__)
sid = SentimentIntensityAnalyzer()
generatedKeys = []

# HTML content for the index.html page
index_html = '''
<!DOCTYPE html>
<html>
<head>
    <title>Text Detector System</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f0f0f0;
        }

        h1 {
            text-align: center;
            color: #007bff;
        }

        .container {
            width: 600px;
            margin: 0 auto;
            background-color: #fff;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            color: #333;
            font-size: 18px;
            margin-bottom: 5px;
        }

        .form-group input[type="text"] {
            width: 100%;
            padding: 10px;
            border: 1px solid #ccc;
            border-radius: 5px;
            font-size: 16px;
        }

        .form-group input[type="submit"] {
            background-color: #007bff;
            color: #fff;
            cursor: pointer;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            font-size: 16px;
        }

        .result {
            margin-top: 30px;
            text-align: center;
        }

        .result p {
            font-size: 18px;
            margin-bottom: 10px;
        }

        /* Colorful Sentiment Results */
        .positive {
            color: green;
        }

        .neutral {
            color: #007bff;
        }

        .negative {
            color: red;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Text Detector System on Docker(final)</h1>
        <form method="post" class="form-group">
            <label for="text">Type a text here:</label>
            <input type="text" id="text" name="text" value="{{ typed_text }}" required>
            <input type="submit" value="Analyze">
        </form>
        {% if result %}
        <div class="result">
            <p>Typed Text: {{ typed_text }}</p>
            <p class="{% if result.compound >= 0.05 %}positive{% elif result.compound <= -0.05 %}negative{% else %}neutral{% endif %}">
                Sentiment: {% if result.compound >= 0.05 %}Positive{% elif result.compound <= -0.05 %}Negative{% else %}Neutral{% endif %}
            </p>
            <p>Compound Score: {{ result.compound }}</p>
            <p class="positive">Positive Score: {{ result.positive }}</p>
            <p class="neutral">Neutral Score: {{ result.neutral }}</p>
            <p class="negative">Negative Score: {{ result.negative }}</p>
        </div>
        {% endif %}
    </div>
</body>
</html>
'''

def random_num():
    while True:
        random_number = random.randint(0, 100000)
        if random_number not in generatedKeys:
            generatedKeys.append(random_number)
            return random_number

@app.route("/", methods=["GET", "POST"])
def analysis_text():
    result = None
    typed_text = ""
    sentiment = ""
    messageKey = ""
    file_path = "/app/sentimentKey.json"
    
    if request.method == "POST":
        typed_text = request.form["text"]
        logging.debug("The text is:{}".format(typed_text))
        sentences = [typed_text]
        ss = sid.polarity_scores(typed_text)
        result = {
            "positive": ss["pos"],
            "neutral": ss["neu"],
            "negative": ss["neg"],
            "compound": ss["compound"],
        }
        if result["compound"] >= 0.05:
            sentiment = "Positive"
        elif result["compound"] <= -0.05:
            sentiment = "Negative"
        else:
            sentiment = "Neutral"
        logging.debug("The sentiment is: {}".format(sentiment))
        messageKey = random_num()
        logging.debug("The messageKey is: {}".format(messageKey))
        ref = db.reference('/')
        current_timestamp = datetime.now()
        timestamp_string = current_timestamp.strftime('%Y-%m-%d %H:%M:%S')
        data = {
          'messageKey': messageKey,
          'result': result,
          'sentiment': sentiment,
          'timeStamp': timestamp_string
        }
        ref.push(data)
        try:
            with open(file_path, 'r') as json_file:
                jsonData = json.load(json_file)
        except FileNotFoundError:
            jsonData = []

        jsonData.append({
          'messageKey': messageKey,
          'result': result,
          'sentiment': sentiment,
          'message': typed_text,
          'timeStamp': timestamp_string
        })

        #Inserting document into a collection
        doc1 = {"messageKey": messageKey, "sentiment": sentiment, "message": typed_text, "result": result, "timeStamp": timestamp_string}
        coll.insert_one(doc1)
        with open(file_path, 'w') as json_file:
            json.dump(jsonData, json_file, indent=4)

    return render_template_string(index_html, typed_text=typed_text, result=result)

if __name__ == "__main__":
    cred = credentials.Certificate('/app/serviceAccountKey.json')
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://fir-1b4c8.firebaseio.com/'
    })
    port = 8000

    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("Invalid port number. Using default port 8080.")
            port = 8000

    app.run(host='0.0.0.0', port=port)
