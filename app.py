from flask import Flask, jsonify, request
import requests
import random
import os
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai

import openmeteo_requests
import requests_cache
from retry_requests import retry

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Allow CORS for all routes

# API KEYS
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")  # OpenWeatherMap API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # OpenAI API Key

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

cache_session = requests_cache.CachedSession(".cache", expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

weather_store = {}  # In-memory dictionary to hold weather data


# Simulate Sensor Data
def get_mock_sensor_data():
    return {
        "soil_moisture": random.uniform(20, 60),  # Soil moisture percentage
        "tank_level": random.uniform(10, 100),  # Tank water level
        "light_level": random.uniform(50, 100),  # Light intensity percentage
        "wind_speed": random.uniform(5, 20),  # Wind speed in mph
    }


@app.route("/fetch_weather", methods=["GET"])
def fetch_weather():
    latitude = request.args.get("lat")
    longitude = request.args.get("lon")

    try:
        url = "https://api.open-meteo.com/v1/forecast"

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": [
                "temperature_2m",
                "relative_humidity_2m",
                "precipitation",
                "rain",
                "showers",
                "snowfall",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
            ],
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
        }
        responses = openmeteo.weather_api(url, params=params)

        response = responses[0]
        current = response.Current()

        print(response)

        weather_data = {
            "current_temperature_2m": current.Variables(0).Value(),
            "current_relative_humidity_2m": current.Variables(1).Value(),
            "current_precipitation": current.Variables(2).Value(),
            "current_rain": current.Variables(3).Value(),
            "current_showers": current.Variables(4).Value(),
            "current_snowfall": current.Variables(5).Value(),
            "current_wind_speed_10m": current.Variables(6).Value(),
            "current_wind_direction_10m": current.Variables(7).Value(),
            "current_wind_gusts_10m": current.Variables(8).Value(),
        }

        weather_store["weather_data"] = weather_data

        return jsonify(weather_data)
    except Exception as e:
        print(e)
        return jsonify({"error": f"Failed to fetch weather data: {str(e)}"}), 500


# Generate AI Insights
def generate_insights(sensor_data, weather_data):
    prompt = f"""
    Based on the following farm data:
    - Temperature: {weather_data['temperature']}°F
    - Humidity: {weather_data['humidity']}%
    - Soil Moisture: {sensor_data['soil_moisture']}%
    - Light Levels: {sensor_data['light_levels']} lux
    - Tank Levels: {sensor_data['tank_levels']}%
    - Weather Conditions: {weather_data['weather']}
    
    Provide actionable recommendations for crop health and irrigation.
    """

    response = model.generate_content(prompt)
    return response.text


@app.route("/simulate", methods=["GET"])
def simulate():
    location = request.args.get("location", "Atlanta")
    sensor_data = get_mock_sensor_data()
    weather_data = fetch_weather(location)
    insights = generate_insights(sensor_data, weather_data)

    return jsonify(
        {"sensor_data": sensor_data, "weather_data": weather_data, "insights": insights}
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
