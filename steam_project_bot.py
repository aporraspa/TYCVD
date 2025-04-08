"""
    Telegram bot to retrieve data from steam, and updates it
    to MONGODB database

    Returns:
        : 
"""
import asyncio
from datetime import datetime
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pymongo import MongoClient

# Telegram Bot Token
TELEGRAM_TOKEN = '' ## CHANGE THIS FOR YOUR OWN TELEGRAM TOKEN

# MongoDB setup
uri = "" #SET UP YOUR OWN MONGDB DATABASE
client = MongoClient(uri)
db = client["Testing"]
collection = db["steam_bot"]

# Steam URL and Chrome Driver Setup
URL = "https://store.steampowered.com/specials?snr=1_4_4__125#tab=TopSellers"
CHROME_DRIVER_PATH = "" #PATH TO CHROME DRIVER CHANGE THIS LINE

options = webdriver.ChromeOptions()
options.add_argument("--headless")

async def start(update: Update, context: CallbackContext):
    """
    Function for testing the connection + expalining the bot commands
    /start command and bot description
"""
    await update.message.reply_text("Hello! I'm your Steam price bot."
                                    "You can use the following commands:\n"
                                    "/search <game_name> <price> -"
                                    "Search for a game by name and target price\n"
                                    "/sales - Get the latest sales from Steam")

async def search_game_by_price(update: Update, context: CallbackContext):
    """
    Command /search with proper exception handling and price extraction logic.
    It expects two arguments: the game title and the target price.
    If the price of the game is under the target price, it prompts the user to save it to the database.
    """
    if len(context.args) < 2:
        await update.message.reply_text("Please provide both the game name and the target price:"
                                        "(e.g., /search 'Devil May Cry 5' 10.00)")
        return

    game_name = " ".join(context.args[:-1])
    try:
        target_price = float(context.args[-1])
    except ValueError:
        await update.message.reply_text("Please provide a valid number for the target price.")
        return

    driver = webdriver.Chrome(service=Service(CHROME_DRIVER_PATH), options=options)
    try:
        driver.get('https://store.steampowered.com/')
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'store_nav_search_term')))
        
        # Find the search box and input the game name
        search_box = driver.find_element(By.ID, 'store_nav_search_term')
        search_box.clear()
        search_box.send_keys(game_name)
        search_box.send_keys(Keys.RETURN)

        # Wait for the search results to load
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'search_resultsRows')))
        
        # Get the search results
        results = driver.find_elements(By.CSS_SELECTOR, '#search_resultsRows a')

        if not results:
            await update.message.reply_text(f"No results found for '{game_name}' on Steam.")
            return

        first_result = results[0]
        title = first_result.find_element(By.CSS_SELECTOR, 'span.title').text.strip()
        price_block = first_result.find_element(By.CSS_SELECTOR, 'div.search_price_discount_combined')

        # Extract the price, checking if there is a discount or a regular price
        try:
            discount_block = price_block.find_element(By.CSS_SELECTOR, 'div.discount_block')
            final_price_element = discount_block.find_element(By.CSS_SELECTOR, 'div.discount_final_price')
        except Exception:
            final_price_element = price_block.find_element(By.CSS_SELECTOR, 'div.search_price')

        final_price = final_price_element.text.strip().replace('€', '').replace(',', '.').strip()
        final_price = float(final_price)

        # If the final price is under or equal to the target price, ask the user to save
        if final_price <= target_price:
            game_data = {
                "title": title,
                "price": final_price,
                "source": "search",
                "created_at": datetime.now()
            }
            context.user_data['pending_save'] = game_data

            # Keyboard for asking whether to save the game
            keyboard = [[InlineKeyboardButton("Yes ✅", callback_data="save_yes"),
                        InlineKeyboardButton("No ❌", callback_data="save_no")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"Game: {title}\nPrice: {final_price}€\n\nDo you want to save this to the database?",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(f"Game: {title} is not under the target price (Current: {final_price}€)")

    except Exception as e:
        await update.message.reply_text(f"Error during search: {e}")
    finally:
        driver.quit()
        
async def sales_from_steam(update: Update, context: CallbackContext):
    """
    Function that takes the 1st 12 special offers from steam

    Args:

    Returns:
        Json: 
            title (string): game title
            discount (string): discount of the game
            old_price (string): price before the discount
            new_price (string): current price
            source (string): commnad used to retrieved it
            "created_at (timestamp): date and hour of the query
    """
    driver = webdriver.Chrome(service=Service(CHROME_DRIVER_PATH), options=options)

    try:
        await update.message.reply_text("Navigating to the Steam sales page..."
                                        "Please wait while I fetch the data.")
        driver.get(URL)

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID,
                                                                        'SaleSection_13268')))

        last_height = driver.execute_script("return document.body.scrollHeight")
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        game_containers = driver.find_elements(By.CSS_SELECTOR, 'div.v9uRg57bwOaPsvAnkXESO')

        games = []
        for game in game_containers[:5]:
            try:
                title = game.find_element(By.CSS_SELECTOR, 'div.StoreSaleWidgetTitle').text
                discount = game.find_element(By.CSS_SELECTOR, 'div.cnkoFkzVCby40gJ0jGGS4').text
                try:
                    old_price = game.find_element(By.CSS_SELECTOR,
                                                'div._3fFFsvII7Y2KXNLDk_krOW').text
                    new_price = game.find_element(By.CSS_SELECTOR,
                                                'div._3j4dI1yA7cRfCvK8h406OB').text
                except Exception:
                    old_price = new_price = "N/A"

                games.append({
                    "title": title,
                    "discount": discount,
                    "old_price": old_price,
                    "new_price": new_price,
                    "source": "sales",
                    "created_at": datetime.now()
                })
            except Exception as e:
                print(f"Error parsing a game: {e}")

        if games:
            context.user_data['pending_save'] = games
            response = "Sales from Steam:\n"
            for game in games:
                response += f"Title: {game['title']}\nDiscount: {game['discount']}\nOld Price: {game['old_price']}\nNew Price: {game['new_price']}\n\n"

            keyboard = [[InlineKeyboardButton("Yes ✅", callback_data="save_yes"),
                        InlineKeyboardButton("No ❌", callback_data="save_no")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(response.strip())
            await update.message.reply_text("Do you want to save these sales to the database?",
                                            reply_markup=reply_markup)
        else:
            await update.message.reply_text("No sale games found.")

    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
    finally:
        driver.quit()

async def handle_save_decision(update: Update, context: CallbackContext):
    """
    This handles the decision made by the user to save the data retrieved to
    the database or not

    Args:

    """
    query = update.callback_query
    await query.answer()
    decision = query.data
    pending = context.user_data.get('pending_save')

    if decision == "save_yes" and pending:
        if isinstance(pending, list):
            result = collection.insert_many(pending)
            await query.edit_message_text(f"✅ Saved {len(result.inserted_ids)}"
                                        "sale games to MongoDB.")
        else:
            result = collection.insert_one(pending)
            await query.edit_message_text(f"✅ Saved '{pending['title']}' to MongoDB.")
    else:
        await query.edit_message_text("🚫 Skipped saving to database.")

    context.user_data['pending_save'] = None

async def main():
    """
    Main function to run the bot
    """
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("search", search_game_by_price))
    application.add_handler(CommandHandler("sales", sales_from_steam))
    application.add_handler(CallbackQueryHandler(handle_save_decision))

    await application.run_polling()

if __name__ == '__main__':
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
