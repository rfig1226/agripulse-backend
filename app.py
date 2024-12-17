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
CORS(app, resources={r"/*": {"origins": "*"}}, methods=["POST", "OPTIONS"])

# API KEYS
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")  # OpenWeatherMap API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # OpenAI API Key

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

cache_session = requests_cache.CachedSession(".cache", expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

weather_store = {}  # In-memory dictionary to hold weather data


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
        }

        weather_store["weather_data"] = weather_data

        return jsonify(weather_data)
    except Exception as e:
        print(e)
        return jsonify({"error": f"Failed to fetch weather data: {str(e)}"}), 500


@app.route("/generate_insights", methods=["POST", "OPTIONS"])
def generate_insights():
    if request.method == "OPTIONS":
        # Respond to preflight request
        return jsonify({"message": "CORS preflight OK"}), 200
    try:
        data = request.get_json()
        crop_data = data.get("crop_data", {})
        latitude = data.get("lat")
        longitude = data.get("lon")
        weather_data = weather_store.get("weather_data", {})

        if not weather_data and latitude and longitude:
            print("Fetching weather data for generate_insights...", flush=True)
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
                ],
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "precipitation_unit": "inch",
            }
            responses = openmeteo.weather_api(url, params=params)
            response = responses[0]
            current = response.Current()

            weather_data = {
                "current_temperature_2m": current.Variables(0).Value(),
                "current_relative_humidity_2m": current.Variables(1).Value(),
                "current_precipitation": current.Variables(2).Value(),
                "current_rain": current.Variables(3).Value(),
                "current_showers": current.Variables(4).Value(),
                "current_snowfall": current.Variables(5).Value(),
                "current_wind_speed_10m": current.Variables(6).Value(),
            }

            weather_store["weather_data"] = weather_data  # Update the weather_store
            weather_data = weather_store.get("weather_data", {})

        print(f"WEATHER DATA: {weather_data}", flush=True)

        prompt = f"""
        Based on the following farm data (crop IoT sensor and environmental):

        1. Sensor and General Data from Crops: 
        - Crop Type: {crop_data.get('cropType', 'N/A')}
        - Field Size: {crop_data.get('fieldSize', 'N/A')} acres
        - Soil Type: {crop_data.get('soilType', 'N/A')}
        - Soil Moisture: {crop_data.get('soilMoisture', 'N/A')}%
        - Temperature: {crop_data.get('temperature', 'N/A')}°F
        - Humidity: {crop_data.get('humidity', 'N/A')}%
        - Light Exposure: {crop_data.get('lightExposure', 'N/A')} hours/day
        - Water Tank Level: {crop_data.get('waterTankLevel', 'N/A')}%
        - Wind Speed: {crop_data.get('windSpeed', 'N/A')} mph
        - Growth Stage: {crop_data.get('growthStage', 'N/A')}
        - Irrigation Type: {crop_data.get('irrigationType', 'N/A')}
        - Planting Date: {crop_data.get('plantingDate', 'N/A')}

        2. Local and Realtime Environmental Data
        - Temperature: {weather_data.get('current_temperature_2m', 'N/A')}°F
        - Humidity: {weather_data.get('current_relative_humidity_2m', 'N/A')}%
        - Wind Speed: {weather_data.get('current_wind_speed_10m', 'N/A')} mph
        - Rainfall: {weather_data.get('current_rain', 'N/A')} inch
        - Showers: {weather_data.get('current_showers', 'N/A')} inch
        - Snowfall: {weather_data.get('current_snowfall', 'N/A')} inch
        - General Precipitation: {weather_data.get('current_precipitation', 'N/A')} inch



        Provide actionable recommendations for crop health, irrigation, and yield.
        If some sensor data is missing,
        please provide whatever insights you can based on the realtime environmental data.
        Not all data will be provided, but from the crop type and environment data alone please give 
        some recommendations and tips. Please don't just say "insufficient data". Please try to be 
        as specific as you can with the recommendations. Also please don't use numbered lists in your
        response, only bullet points, bolded headers, and paragraphs.
        """

        response = model.generate_content(prompt)
        insights = response.text.strip()
        print(insights)

        return jsonify({"insights": insights})
    except Exception as e:
        print(e)
        return jsonify({"error": f"Failed to fetch weather data: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port, debug=True)
