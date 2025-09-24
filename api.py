from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_caching import Cache
import requests
from datetime import datetime, timedelta
import os

app = Flask(__name__, static_folder='.', static_url_path='')

# Fix CORS configuration - allow all origins for simplicity
CORS(app, resources={r"/*": {"origins": "*"}})

# Configure cache
cache = Cache(app, config={
    'CACHE_TYPE': 'simple',
    'CACHE_DEFAULT_TIMEOUT': 300  # 5 minutes
})

# API configuration - Use environment variable for security
API_KEY = os.environ.get('OPENWEATHER_API_KEY', 'a9d760831c42b50115855cb5e828461b')
if not API_KEY or API_KEY == 'a9d760831c42b50115855cb5e828461b':
    print("WARNING: Using default API key. Please set OPENWEATHER_API_KEY environment variable.")

GEOCODE_URL = "https://api.openweathermap.org/geo/1.0/direct"
REVERSE_GEOCODE_URL = "https://api.openweathermap.org/geo/1.0/reverse"
CURRENT_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
AIR_POLLUTION_URL = "https://api.openweathermap.org/data/2.5/air_pollution"

# Serve the main HTML file
@app.route('/')
def home():
    return send_from_directory('.', 'index.html')

# Serve static files
@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

@app.route('/get_weather', methods=['GET', 'POST'])
def get_weather():
    try:
        # Check if API key is available
        if not API_KEY:
            return jsonify({'error': 'OpenWeather API key not configured'}), 500
            
        if request.method == 'POST':
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400
                
            city = data.get('city')
            
            if not city:
                return jsonify({'error': 'City name is required'}), 400
            
            geo_data = get_geocode_data(city)
            if not geo_data:
                return jsonify({'error': f'Could not find location for city: {city}'}), 404
                
            lat, lon = geo_data['lat'], geo_data['lon']
            location_info = {
                'city': geo_data.get('name', city),
                'country': geo_data.get('country', ''),
                'state': geo_data.get('state', ''),
                'coordinates': {'lat': lat, 'lon': lon}
            }
        else:  # GET request with coordinates
            lat = request.args.get('lat')
            lon = request.args.get('lon')
            
            if not lat or not lon:
                return jsonify({'error': 'Latitude and longitude are required'}), 400
                
            try:
                lat = float(lat)
                lon = float(lon)
            except ValueError:
                return jsonify({'error': 'Invalid coordinates'}), 400
                
            geo_data = get_reverse_geocode_data(lat, lon)
            location_info = {
                'city': geo_data.get('name', 'Current Location') if geo_data else 'Current Location',
                'country': geo_data.get('country', '') if geo_data else '',
                'state': geo_data.get('state', '') if geo_data else '',
                'coordinates': {'lat': lat, 'lon': lon}
            }
        
        current = fetch_current_weather(lat, lon)
        forecast = fetch_5day_forecast(lat, lon)
        air_quality = fetch_air_quality(lat, lon)
        
        return jsonify({
            'current': current,
            'forecast': forecast,
            'air_quality': air_quality,
            'location': location_info,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except requests.exceptions.RequestException as e:
        return jsonify({'error': 'Weather service unavailable', 'details': str(e)}), 503
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/get_hourly_forecast', methods=['GET'])
def get_hourly_forecast():
    try:
        # Check if API key is available
        if not API_KEY:
            return jsonify({'error': 'OpenWeather API key not configured'}), 500
            
        lat = request.args.get('lat')
        lon = request.args.get('lon')
        
        if not lat or not lon:
            return jsonify({'error': 'Latitude and longitude are required'}), 400
            
        try:
            lat = float(lat)
            lon = float(lon)
        except ValueError:
            return jsonify({'error': 'Invalid coordinates'}), 400
            
        params = {
            'lat': lat,
            'lon': lon,
            'units': 'metric',
            'appid': API_KEY
        }
        
        response = requests.get(FORECAST_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        return jsonify(data)
        
    except requests.exceptions.RequestException as e:
        return jsonify({'error': 'Forecast service unavailable', 'details': str(e)}), 503
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

def get_geocode_data(city):
    city = city.strip()
    params = {
        'q': city,
        'limit': 10,
        'appid': API_KEY
    }
    try:
        response = requests.get(GEOCODE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            print(f"No geocoding results for city: {city}")
            return None
            
        # Find the best match
        for result in data:
            if result.get('name', '').lower() == city.lower():
                return {
                    'name': result.get('name'),
                    'country': result.get('country', ''),
                    'state': result.get('state', ''),
                    'lat': result.get('lat'),
                    'lon': result.get('lon')
                }
                
        # Fallback to first result
        return {
            'name': data[0].get('name'),
            'country': data[0].get('country', ''),
            'state': data[0].get('state', ''),
            'lat': data[0].get('lat'),
            'lon': data[0].get('lon')
        }
        
    except requests.exceptions.RequestException as e:
        print(f"Geocoding error for city {city}: {str(e)}")
        return None

def get_reverse_geocode_data(lat, lon):
    params = {
        'lat': lat,
        'lon': lon,
        'limit': 10,
        'appid': API_KEY
    }
    try:
        response = requests.get(REVERSE_GEOCODE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            return None
            
        # Find the most relevant result
        for result in sorted(data, key=lambda x: -x.get('importance', 0)):
            if result.get('local_names'):
                name = result['local_names'].get('en') or result.get('name')
                return {
                    'name': name,
                    'country': result.get('country', ''),
                    'state': result.get('state', '')
                }
        
        # Fallback to first result
        return {
            'name': data[0].get('name'),
            'country': data[0].get('country', ''),
            'state': data[0].get('state', '')
        }
        
    except requests.exceptions.RequestException as e:
        print(f"Reverse geocoding error: {str(e)}")
        return None

def fetch_current_weather(lat, lon):
    params = {
        'lat': lat,
        'lon': lon,
        'units': 'metric',
        'appid': API_KEY
    }
    response = requests.get(CURRENT_WEATHER_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    
    return {
        'temp': round(data['main']['temp'], 1),
        'feels_like': round(data['main']['feels_like'], 1),
        'description': data['weather'][0]['description'],
        'icon': data['weather'][0]['icon'],
        'humidity': data['main']['humidity'],
        'wind': round(data['wind']['speed'] * 3.6, 1),
        'pressure': data['main']['pressure'],
        'visibility': round(data.get('visibility', 0) / 1000, 1),
        'sunrise': datetime.fromtimestamp(data['sys']['sunrise']).strftime('%H:%M'),
        'sunset': datetime.fromtimestamp(data['sys']['sunset']).strftime('%H:%M'),
        'observation_time': datetime.fromtimestamp(data['dt']).strftime('%H:%M UTC')
    }

def fetch_5day_forecast(lat, lon):
    params = {
        'lat': lat,
        'lon': lon,
        'units': 'metric',
        'appid': API_KEY
    }
    response = requests.get(FORECAST_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    
    # Group by day
    daily_forecasts = {}
    for item in data['list']:
        date = datetime.fromtimestamp(item['dt']).strftime('%Y-%m-%d')
        if date not in daily_forecasts:
            daily_forecasts[date] = {
                'temp_min': item['main']['temp_min'],
                'temp_max': item['main']['temp_max'],
                'conditions': [],
                'icons': set()
            }
        else:
            daily_forecasts[date]['temp_min'] = min(daily_forecasts[date]['temp_min'], item['main']['temp_min'])
            daily_forecasts[date]['temp_max'] = max(daily_forecasts[date]['temp_max'], item['main']['temp_max'])
        
        daily_forecasts[date]['conditions'].append(item['weather'][0]['description'])
        daily_forecasts[date]['icons'].add(item['weather'][0]['icon'])
    
    # Process for response
    forecast_days = []
    today = datetime.now().strftime('%Y-%m-%d')
    
    for date, values in daily_forecasts.items():
        if date == today:
            continue
            
        forecast_days.append({
            'date': date,
            'day_name': datetime.strptime(date, '%Y-%m-%d').strftime('%A'),
            'temp_min': round(values['temp_min'], 1),
            'temp_max': round(values['temp_max'], 1),
            'main_condition': max(set(values['conditions']), key=values['conditions'].count),
            'icon': next(iter(values['icons']))
        })
    
    return forecast_days[:5]

def fetch_air_quality(lat, lon):
    params = {
        'lat': lat,
        'lon': lon,
        'appid': API_KEY
    }
    try:
        response = requests.get(AIR_POLLUTION_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data or 'list' not in data or len(data['list']) == 0:
            return None
        
        aqi = data['list'][0]['main']['aqi']
        aqi_levels = {
            1: 'Good',
            2: 'Fair',
            3: 'Moderate',
            4: 'Poor',
            5: 'Very Poor'
        }
        
        return {
            'aqi': aqi,
            'level': aqi_levels.get(aqi, 'Unknown'),
            'components': data['list'][0]['components']
        }
    except requests.exceptions.RequestException as e:
        print(f"Air quality fetch error: {str(e)}")
        return None

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# Health check endpoint
@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    print(f"Starting server on port {port} with debug={debug}")
    app.run(host='0.0.0.0', port=port, debug=debug)
