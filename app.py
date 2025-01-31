from flask import Flask, render_template, request, jsonify, abort
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
import os
import timeago
from flask_caching import Cache
import logging
from logging.handlers import RotatingFileHandler

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Configure logging
if not os.path.exists('logs'):
    os.mkdir('logs')
file_handler = RotatingFileHandler('logs/news_app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('News App startup')

# Configure caching
cache = Cache(app, config={
    'CACHE_TYPE': 'simple',
    'CACHE_DEFAULT_TIMEOUT': 300  # 5 minutes cache
})

# Constants
NEWS_API_KEY = os.getenv('NEWS_API_KEY')
if not NEWS_API_KEY:
    raise ValueError("NEWS_API_KEY not found in environment variables")

BASE_URL = 'https://newsapi.org/v2'

CATEGORIES = [
    'general', 'business', 'technology', 'entertainment',
    'sports', 'science', 'health'
]

COUNTRIES = {
    'us': 'United States',
    'gb': 'United Kingdom',
    'in': 'India',
    'au': 'Australia',
    'ca': 'Canada',
    'nz': 'New Zealand'
}

def format_date(date_str):
    """Format date string to timeago format"""
    try:
        date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%SZ')
        return timeago.format(date, datetime.utcnow())
    except Exception as e:
        app.logger.error(f"Error formatting date: {str(e)}")
        return date_str

def fetch_news(endpoint, params=None):
    """
    Fetch news from News API
    
    Args:
        endpoint (str): API endpoint to fetch from
        params (dict): Query parameters for the API request
        
    Returns:
        dict: JSON response from the API
        
    Raises:
        abort: HTTP error status if request fails
    """
    if params is None:
        params = {}
    
    params['apiKey'] = NEWS_API_KEY
    url = f'{BASE_URL}/{endpoint}'
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error fetching news from {url}: {str(e)}")
        if response.status_code == 429:
            abort(429)
        abort(500, description="Error fetching news")

@app.template_filter('timeago')
def timeago_filter(date_str):
    return format_date(date_str)

@app.route('/')
@cache.cached(timeout=300)
def home():
    """Home page with top headlines from different categories"""
    try:
        top_headlines = fetch_news('top-headlines', {
            'country': 'us',
            'pageSize': 6
        })
        
        category_news = {}
        for category in CATEGORIES:
            news = fetch_news('top-headlines', {
                'category': category,
                'pageSize': 4,
                'country': 'us'
            })
            category_news[category] = news.get('articles', [])
        
        return render_template('index.html',
                             top_headlines=top_headlines.get('articles', []),
                             category_news=category_news,
                             categories=CATEGORIES,
                             countries=COUNTRIES)
    except Exception as e:
        app.logger.error(f"Error in home route: {str(e)}")
        abort(500)

@app.route('/category/<category>')
@cache.cached(timeout=300)
def category(category):
    """Category-specific news page"""
    try:
        if category not in CATEGORIES:
            abort(404)
            
        news = fetch_news('top-headlines', {
            'category': category,
            'pageSize': 30,
            'country': 'us'
        })
        
        return render_template('category.html',
                             category=category,
                             articles=news.get('articles', []),
                             categories=CATEGORIES,
                             countries=COUNTRIES)
    except Exception as e:
        app.logger.error(f"Error in category route: {str(e)}")
        abort(500)

@app.route('/search')
def search():
    """Search page"""
    try:
        query = request.args.get('q', '')
        if not query:
            return render_template('search.html',
                                 articles=[],
                                 categories=CATEGORIES,
                                 countries=COUNTRIES)
        
        news = fetch_news('everything', {
            'q': query,
            'pageSize': 30,
            'sortBy': 'relevancy',
            'language': 'en'
        })
        
        return render_template('search.html',
                             query=query,
                             articles=news.get('articles', []),
                             categories=CATEGORIES,
                             countries=COUNTRIES)
    except Exception as e:
        app.logger.error(f"Error in search route: {str(e)}")
        abort(500)

@app.route('/sources')
@cache.cached(timeout=3600)  # Cache for 1 hour
def sources():
    """News sources page"""
    try:
        sources_data = fetch_news('top-headlines/sources')
        
        # Group sources by category
        categorized_sources = {}
        for source in sources_data.get('sources', []):
            category = source.get('category', 'general')
            if category not in categorized_sources:
                categorized_sources[category] = []
            categorized_sources[category].append(source)
        
        return render_template('sources.html',
                             categorized_sources=categorized_sources,
                             categories=CATEGORIES,
                             countries=COUNTRIES)
    except Exception as e:
        app.logger.error(f"Error in sources route: {str(e)}")
        abort(500)

@app.route('/country/<country_code>')
@cache.cached(timeout=300)
def country_news(country_code):
    """Country-specific news page"""
    try:
        if country_code not in COUNTRIES:
            abort(404)
            
        news = fetch_news('top-headlines', {
            'country': country_code,
            'pageSize': 30
        })
        
        return render_template('country.html',
                             country_code=country_code,
                             country_name=COUNTRIES[country_code],
                             articles=news.get('articles', []),
                             categories=CATEGORIES,
                             countries=COUNTRIES)
    except Exception as e:
        app.logger.error(f"Error in country_news route: {str(e)}")
        abort(500)

@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html',
                         categories=CATEGORIES,
                         countries=COUNTRIES), 404

@app.errorhandler(429)
def too_many_requests(error):
    return render_template('429.html',
                         categories=CATEGORIES,
                         countries=COUNTRIES), 429

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f'Server Error: {str(error)}')
    return render_template('500.html',
                         categories=CATEGORIES,
                         countries=COUNTRIES), 500

@app.context_processor
def utility_processor():
    """Make common variables available to all templates"""
    return dict(
        categories=CATEGORIES,
        countries=COUNTRIES
    )

if __name__ == '__main__':
    app.run(
        debug=os.getenv('FLASK_ENV') == 'development',
        host=os.getenv('FLASK_HOST', '0.0.0.0'),
        port=int(os.getenv('FLASK_PORT', 5000))
    )