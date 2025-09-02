import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
import logging
import tweepy
import re

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TwitterFollowerBot:
    def __init__(self):
        # Configuration
        self.target_username = os.getenv('TARGET_USERNAME', 'elonmusk')
        self.data_file = 'follower_data.json'
        
        # Twitter API credentials
        self.bearer_token = os.getenv('TWITTER_BEARER_TOKEN')
        self.api_key = os.getenv('TWITTER_API_KEY')
        self.api_secret = os.getenv('TWITTER_API_SECRET')
        self.access_token = os.getenv('TWITTER_ACCESS_TOKEN')
        self.access_token_secret = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
        
        # Headers for web scraping
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # Initialize Twitter API
        self.client = None
        self.setup_twitter_api()
    
    def setup_twitter_api(self):
        """Initialize Twitter API client"""
        try:
            if not all([self.bearer_token, self.api_key, self.api_secret, self.access_token, self.access_token_secret]):
                logger.error("Missing Twitter API credentials")
                return False
            
            self.client = tweepy.Client(
                bearer_token=self.bearer_token,
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_token_secret,
                wait_on_rate_limit=True
            )
            
            # Test authentication
            me = self.client.get_me()
            if me.data:
                logger.info(f"✓ Twitter API authenticated as: @{me.data.username}")
                return True
            else:
                logger.error("✗ Twitter API authentication failed")
                return False
            
        except Exception as e:
            logger.error(f"✗ Twitter API setup failed: {e}")
            return False
    
    def get_follower_count(self, username):
        """Scrape follower count from multiple sources"""
        logger.info(f"Getting follower count for @{username}")
        
        # Method 1: Try Nitter instances
        nitter_instances = [
            "https://nitter.net",
            "https://nitter.it",
            "https://nitter.privacydev.net",
            "https://nitter.fdn.fr", 
            "https://nitter.kavin.rocks",
            "https://nitter.1d4.us",
            "https://nitter.42l.fr",
            "https://nitter.pussthecat.org"
        ]
        
        for instance in nitter_instances:
            count = self.try_nitter_instance(instance, username)
            if count:
                return count
        
        # Method 2: Try Social Blade
        count = self.try_social_blade(username)
        if count:
            return count
        
        logger.error("❌ All scraping methods failed")
        return None
    
    def try_nitter_instance(self, instance, username):
        """Try to get follower count from a Nitter instance"""
        try:
            url = f"{instance}/{username}"
            logger.info(f"Trying {instance}")

            response = requests.get(url, headers=self.headers, timeout=15)
            
            if response.status_code != 200:
                logger.info(f"✗ {instance} returned status {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Method 1: Look for profile-stat-num spans
            stats = soup.find_all('span', class_='profile-stat-num')
            if len(stats) >= 2:
                # Usually: [tweets, following, followers] or [tweets, followers, following]
                for i, stat in enumerate(stats):
                    count_text = stat.get_text().strip()
                    count = self.parse_count(count_text)
                    if count and count > 1000:  # Basic sanity check
                        # Check if this is likely the follower count by looking at surrounding text
                        parent = stat.find_parent()
                        if parent and 'followers' in parent.get_text().lower():
                            logger.info(f"✓ Found follower count from {instance}: {count:,}")
                            return count
            
            # Method 2: Look for specific follower text
            follower_elements = soup.find_all(string=re.compile(r'[\d,KM.]+\s*[Ff]ollowers?'))
            for element in follower_elements:
                match = re.search(r'([\d,KM.]+)', element)
                if match:
                    count = self.parse_count(match.group(1))
                    if count and count > 1000:
                        logger.info(f"✓ Found follower count from {instance}: {count:,}")
                        return count
            
            # Method 3: Look for profile-stat divs
            stat_divs = soup.find_all('div', class_='profile-stat')
            for div in stat_divs:
                if 'follower' in div.get_text().lower():
                    num_span = div.find('span', class_='profile-stat-num')
                    if num_span:
                        count = self.parse_count(num_span.get_text().strip())
                        if count and count > 1000:
                            logger.info(f"✓ Found follower count from {instance}: {count:,}")
                            return count
            
            logger.info(f"✗ No follower count found on {instance}")
            return None
            
        except requests.exceptions.Timeout:
            logger.warning(f"✗ {instance} timed out")
            return None
        except requests.exceptions.ConnectionError:
            logger.warning(f"✗ {instance} connection failed")
            return None
        except Exception as e:
            logger.warning(f"✗ {instance} failed: {str(e)[:100]}")
            return None
    
    def try_social_blade(self, username):
        """Try to get follower count from Social Blade"""
        try:
            url = f"https://socialblade.com/twitter/user/{username}"
            logger.info("Trying Social Blade")
            
            response = requests.get(url, headers=self.headers, timeout=15)
            
            if response.status_code != 200:
                logger.info(f"✗ Social Blade returned status {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for numbers that could be follower counts
            potential_numbers = []
            
            # Find all bold numbers (Social Blade uses bold for stats)
            bold_elements = soup.find_all(['b', 'strong'])
            for element in bold_elements:
                text = element.get_text().strip()
                if re.match(r'^\d{1,3}(,\d{3})*$', text):
                    num = int(text.replace(',', ''))
                    if 1000 <= num <= 500000000:  # Reasonable range
                        potential_numbers.append(num)
            
            # Also check spans with bold styling
            span_elements = soup.find_all('span', style=re.compile(r'font-weight:\s*bold'))
            for element in span_elements:
                text = element.get_text().strip()
                if re.match(r'^\d{1,3}(,\d{3})*$', text):
                    num = int(text.replace(',', ''))
                    if 1000 <= num <= 500000000:
                        potential_numbers.append(num)
            
            if potential_numbers:
                # Return the largest number (most likely to be followers)
                follower_count = max(potential_numbers)
                logger.info(f"✓ Found follower count from Social Blade: {follower_count:,}")
                return follower_count
            
            logger.info("✗ No follower count found on Social Blade")
            return None
            
        except Exception as e:
            logger.warning(f"✗ Social Blade failed: {e}")
            return None
    
    def parse_count(self, count_text):
        """Parse follower count text (handles K, M, B notation)"""
        if not count_text:
            return None
            
        count_text = count_text.strip().upper().replace(',', '').replace(' ', '')
        
        try:
            if 'K' in count_text:
                base = float(count_text.replace('K', ''))
                return int(base * 1000)
            elif 'M' in count_text:
                base = float(count_text.replace('M', ''))
                return int(base * 1000000)
            elif 'B' in count_text:
                base = float(count_text.replace('B', ''))
                return int(base * 1000000000)
            else:
                return int(count_text)
        except (ValueError, TypeError):
            return None
    
    def load_data(self):
        """Load historical follower data"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    logger.info(f"Loaded historical data with {len(data)} accounts")
                    return data
            else:
                logger.info("No historical data found, starting fresh")
                return {}
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            return {}
    
    def save_data(self, data):
        """Save follower data to file"""
        try:
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("Data saved successfully")
        except Exception as e:
            logger.error(f"Error saving data: {e}")
    
    def calculate_change(self, current_count, history):
        """Calculate follower change from ~24 hours ago"""
        if not history:
            return None, None, None
        
        now = datetime.now()
        target_time = now - timedelta(hours=24)
        
        # Find the closest record to 24 hours ago
        closest_record = None
        min_diff = float('inf')
        
        for record in history:
            record_time = datetime.fromisoformat(record['timestamp'])
            diff = abs((record_time - target_time).total_seconds())
            if diff < min_diff:
                min_diff = diff
                closest_record = record
        
        if closest_record:
            change = current_count - closest_record['followers_count']
            hours_ago = (now - datetime.fromisoformat(closest_record['timestamp'])).total_seconds() / 3600
            return change, hours_ago, closest_record['followers_count']
        
        return None, None, None
    
    def format_tweet(self, username, current_count, change, hours_ago, previous_count):
        """Format tweet message (within 280 characters)"""
        current_formatted = f"{current_count:,}"
        
        if change is None:
            tweet = f"📊 @{username} currently has {current_formatted} followers.\n\n(First tracking)\n\n#FollowerTracker"
            return tweet
        
        change_formatted = f"{abs(change):,}"
        
        if change > 0:
            emoji = "📈"
            change_text = f"+{change_formatted}"
            verb = "gained"
        elif change < 0:
            emoji = "📉"
            change_text = f"-{change_formatted}"
            verb = "lost"
        else:
            emoji = "➡️"
            change_text = "0"
            verb = "no change"
        
        # Format tweet
        tweet = f"{emoji} @{username} {verb} {change_text} followers in ~{hours_ago:.0f}h\n\n"
        tweet += f"📊 Current: {current_formatted}\n"
        tweet += f"📈 Change: {change_text}\n\n"
        tweet += f"#FollowerTracker"
        
        # Check character limit
        if len(tweet) > 280:
            # Shorter version
            tweet = f"{emoji} @{username} {verb} {change_text} followers\n\n"
            tweet += f"{current_formatted} ({change_text})\n\n"
            tweet += f"#FollowerTracker"
        
        return tweet
    
    def post_tweet(self, message):
        """Post tweet to Twitter"""
        if not self.client:
            logger.error("Twitter API client not available")
            return False
        
        try:
            response = self.client.create_tweet(text=message)
            if response.data:
                tweet_id = response.data['id']
                tweet_url = f"https://twitter.com/i/status/{tweet_id}"
                logger.info(f"✓ Tweet posted successfully: {tweet_url}")
                return True
            else:
                logger.error("✗ Tweet response has no data")
                return False
            
        except Exception as e:
            logger.error(f"✗ Error posting tweet: {e}")
            return False
    
    def run(self):
        """Main execution function"""
        logger.info("=" * 60)
        logger.info(f"Starting follower tracking for @{self.target_username}")
        logger.info("=" * 60)
        
        # Get current follower count
        current_count = self.get_follower_count(self.target_username)
        if not current_count:
            # Post error tweet
            if self.client:
                error_tweet = f"❌ Could not get follower count for @{self.target_username} today. Will try again tomorrow! #FollowerTracker"
                # self.post_tweet(error_tweet)
            return False
        
        logger.info(f"✓ Current followers: {current_count:,}")
        
        # Load historical data
        all_data = self.load_data()
        user_history = all_data.get(self.target_username, [])
        
        # Calculate change from 24 hours ago
        change, hours_ago, previous_count = self.calculate_change(current_count, user_history)
        
        # Add new record
        new_record = {
            'followers_count': current_count,
            'timestamp': datetime.now().isoformat()
        }
        user_history.append(new_record)
        
        # Keep only last 30 days to save space
        cutoff = datetime.now() - timedelta(days=30)
        user_history = [
            record for record in user_history 
            if datetime.fromisoformat(record['timestamp']) > cutoff
        ]
        
        # Save updated data
        all_data[self.target_username] = user_history
        self.save_data(all_data)
        
        # Format tweet message
        tweet_text = self.format_tweet(
            self.target_username, 
            current_count, 
            change, 
            hours_ago, 
            previous_count
        )
        
        # Display tweet preview
        logger.info("Tweet to post:")
        logger.info("=" * 50)
        logger.info(tweet_text)
        logger.info(f"Characters: {len(tweet_text)}/280")
        logger.info("=" * 50)
        
        # Post tweet
        success = self.post_tweet(tweet_text)
        
        if success:
            logger.info("✅ Bot run completed successfully!")
        else:
            logger.error("❌ Failed to post tweet")
        
        return success

if __name__ == "__main__":
    bot = TwitterFollowerBot()
    bot.run()
