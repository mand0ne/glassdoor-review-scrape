import logging.config
import time

import numpy as np
import pandas as pd
import selenium
from selenium import webdriver as wd
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By

from schema import SCHEMA

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
logger.addHandler(ch)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(lineno)d:%(filename)s(%(process)d) - %(message)s')
ch.setFormatter(formatter)
logging.getLogger('selenium').setLevel(logging.CRITICAL)
logging.getLogger('selenium').setLevel(logging.CRITICAL)

# Konfiguracija
username = 'USERNAME'  # Podaci za prijavu na Glassdoor
password = 'PASSWORD'
headless_mode = True  # Sakrij Chrome dok scrapeas, za debug stavit False, pratit sta se desava

# Direktan URL do prve stranice recenzija!
# Na google ukucati npr. Amazon Glassdoor Reviews i trebao bi to odmah biti prvi url koji izadje
url = 'https://www.glassdoor.com/Reviews/Netflix-Reviews-E11891.htm'

limit = 25
filename = 'netflix_reviews.csv'


def scrape(field, review, author):
    def scrape_date(review):
        try:
            res = author.find_element(by=By.CLASS_NAME, value='authorJobTitle').text.split('-')[0]
            res = res.replace(',', '').strip()
        except Exception:
            res = np.nan
        return res

    def scrape_emp_title(review):
        if 'Anonymous Employee' not in review.text:
            try:
                res = author.find_element(by=By.CLASS_NAME, value='authorJobTitle').text.split('-')[1]
                res = res.strip()
            except Exception:
                res = np.nan
        else:
            res = "Anonymous"
        return res

    def scrape_location(review):
        split_text = review.text.split('\n')
        split_text = split_text[4]
        if 'in' in split_text:
            try:
                res = author.find_element(by=By.CLASS_NAME, value='authorLocation').text
                res = res.strip()
            except Exception:
                res = np.nan
        else:
            res = np.nan
        return res

    def scrape_rev_title(review):
        return review.find_element(by=By.CLASS_NAME, value='reviewLink').text.strip('"')

    def expand_show_more(section):
        try:
            more_link = section.find_element(by=By.CLASS_NAME, value='v2__EIReviewDetailsV2__continueReading')
            more_link.click()
        except Exception:
            pass

    def scrape_pros(review):
        try:
            pros = review.find_element(by=By.CLASS_NAME, value='gdReview')
            expand_show_more(pros)

            pro_index = pros.text.find('Pros')
            con_index = pros.text.find('Cons')
            res = pros.text[pro_index + 5: con_index]
            res = res.strip()
        except Exception:
            res = np.nan
        return res

    def scrape_cons(review):
        try:
            cons = review.find_element(by=By.CLASS_NAME, value='gdReview')
            expand_show_more(cons)

            con_index = cons.text.find('Cons')
            continue_index = cons.text.find('Advice to Management')
            if continue_index == -1:
                help_container = review.find_element(by=By.CLASS_NAME,
                                                     value='common__EiReviewDetailsStyle__socialHelpfulcontainer')
                continue_index = cons.text.find(help_container.text)
            res = cons.text[con_index + 5: continue_index]
            res = res.strip()
        except Exception:
            res = np.nan
        return res

    def scrape_advice(review):
        try:
            advice = review.find_element(by=By.CLASS_NAME, value='gdReview')
            expand_show_more(advice)

            help_container = review.find_element(by=By.CLASS_NAME,
                                                 value='common__EiReviewDetailsStyle__socialHelpfulcontainer')
            advice_index = advice.text.find('Advice to Management')

            if advice_index != -1:
                helpful_index = advice.text.find(help_container.text)
                res = advice.text[advice_index + 21: helpful_index]
            else:
                res = np.nan

            res = res.strip()
        except Exception:
            res = np.nan
        return res

    def scrape_overall_rating(review):
        try:
            rating = review.text.split('\n')[0]
            res = float(rating)
        except Exception:
            res = np.nan
        return res

    funcs = [
        scrape_date,
        scrape_emp_title,
        scrape_location,
        scrape_rev_title,
        scrape_overall_rating,
        scrape_pros,
        scrape_cons,
        scrape_advice
    ]

    fdict = dict((s, f) for (s, f) in zip(SCHEMA, funcs))
    return fdict[field](review)


def extract_from_page():
    def is_featured(review):
        try:
            review.find_element(by=By.CLASS_NAME, value='featuredFlag')
            return True
        except selenium.common.exceptions.NoSuchElementException:
            return False

    def extract_review(review):
        try:
            author = review.find_element(by=By.CLASS_NAME, value='authorInfo')
        except:
            return None  # Uracunaj recenzije koje su blokirane
        res = {}

        for field in SCHEMA:
            res[field] = scrape(field, review, author)

        assert set(res.keys()) == set(SCHEMA)
        return res

    logger.info(f'Izvlacim recenzije sa strane {page[0]}')

    res = pd.DataFrame([], columns=SCHEMA)

    reviews = browser.find_elements(by=By.CLASS_NAME, value='empReview')
    logger.info(f'Pronadjeno {len(reviews)} recenzija na strani {page[0]}')

    # Osvjezi stranicu ako se nisu ucitale recenzije, ako opet faila gasi sve
    if len(reviews) < 1:
        browser.refresh()
        time.sleep(5)
        reviews = browser.find_elements(by=By.CLASS_NAME, value='empReview')
        logger.info(f'Pronadjeno {len(reviews)} recenzija na strani {page[0]}')
        if len(reviews) < 1:
            valid_page[0] = False  # Ima li ista?

    for review in reviews:
        if not is_featured(review):
            data = extract_review(review)
            if data is not None:
                logger.info(f'Dohvaceni podaci za "{data["review_title"]}"({data["date"]})')
                res.loc[idx[0]] = data
            else:
                logger.info('Odbacujem blokiranu recenziju')
        else:
            logger.info('Odbacujem izdvojenu recenziju')
        idx[0] = idx[0] + 1

    return res


def more_pages():
    try:
        current = browser.find_element(by=By.CLASS_NAME, value='selected')
        pages = browser.find_element(by=By.CLASS_NAME, value='pageContainer').text.split()
        if int(pages[-1]) != int(current.text):
            return True
        else:
            return False
    except selenium.common.exceptions.NoSuchElementException:
        return False


def go_to_next_page():
    logger.info(f'Prelazim na stranicu {page[0] + 1}')
    next_ = browser.find_element(by=By.CLASS_NAME, value='nextButton')
    ActionChains(browser).click(next_).perform()
    time.sleep(5)  # Pricekaj jos malko
    page[0] = page[0] + 1


def sign_in():
    logger.info(f'Prijavljem se kao {username}')

    login_url = 'https://www.glassdoor.com/profile/login_input.htm'
    browser.get(login_url)

    email_field = browser.find_element(by=By.NAME, value='username')
    password_field = browser.find_element(by=By.NAME, value='password')
    submit_btn = browser.find_element(by=By.XPATH, value='//button[@type="submit"]')

    email_field.send_keys(username)
    password_field.send_keys(password)
    submit_btn.click()

    time.sleep(3)
    browser.get(url)


def get_browser():
    logger.info('Konfiguracija pretrazivaca')
    chrome_options = wd.ChromeOptions()

    if headless_mode:
        chrome_options.add_argument('--headless')

    chrome_options.add_argument('log-level=3')
    browser = wd.Chrome(options=chrome_options)
    return browser


def get_current_page():
    logger.info('Dohvacam trenutni broj stranice')
    current = browser.find_element(by=By.CLASS_NAME, value='selected')
    return int(current.text)


browser = get_browser()
page = [1]
idx = [0]
valid_page = [True]


def main():
    start = time.time()
    logger.info(f'Scrapeam do {limit} recenzija.')

    sign_in()
    browser.get(url)
    page[0] = get_current_page()
    logger.info(f'Pocinjem od strane {page[0]:,}.')
    time.sleep(1)

    reviews_df = extract_from_page()
    res = pd.DataFrame([], columns=SCHEMA)
    res = res.append(reviews_df)

    while more_pages() and \
            len(res) < limit and \
            valid_page[0]:
        go_to_next_page()
        try:
            reviews_df = extract_from_page()
            res = res.append(reviews_df)
        except:
            break

    logger.info(f'Zapisujem {len(res)} recenzija u fajl {filename}')
    res.to_csv(filename, index=False, encoding='utf-8')

    end = time.time()
    logger.info(f'Zavrseno za {end - start} sekundi')


if __name__ == '__main__':
    main()
