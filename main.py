from argparse import ArgumentParser
import logging.config
import time

import numpy as np
import pandas
import pandas as pd
import math

import selenium
from selenium import webdriver as wd
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By

from schema import SCHEMA

parser = ArgumentParser()
parser.add_argument('-u', '--url', help='URL prve stranice Glassdoor recenzija kompanije')
parser.add_argument('-f', '--file', help='Izlazna CSV datoteka')
parser.add_argument('--headless', action='store_true', help='Pokreni Chrome u headless rezim')
parser.add_argument('-e', '--email', help='E-mail za Glassdoor')
parser.add_argument('-p', '--password', help='Lozinka za Glassdoor')
parser.add_argument('-l', '--limit', default=1000, action='store', type=int, help='Recenzija za dohvatiti')
args = parser.parse_args()

# if not args.url:
#     raise Exception('URL prve stranice recenzija nije naveden!')
# if not args.file:
#     raise Exception('Izlazna CSV datoteka nije navedena!')
# if not args.email:
#     raise Exception('Korisnicki e-mail za GD nije naveden!')
# if not args.password:
#     raise Exception('Korisnicka lozinka za GD nije navedena!')

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
username = args.email  # Podaci za prijavu na Glassdoor
password = args.password
headless_mode = args.headless  # Sakrij Chrome dok scrapeas, za debug stavit False, pratit sta se desava

# Direktan URL do prve stranice recenzija!
# Na google ukucati npr. Amazon Glassdoor Reviews i trebao bi to odmah biti prvi url koji izadje
url = args.url
limit = args.limit
filename = args.file

low_order_filter = "?sort.sortType=OR&sort.ascending=true&filter.iso3Language=eng"
high_order_filter = "?sort.sortType=OR&sort.ascending=false&filter.iso3Language=eng"
popular_order_filter = "?filter.iso3Language=eng"


def scrape(field, review, author):
    def scrape_review_date(review):
        try:
            res = author.find_element(by=By.CLASS_NAME, value='authorJobTitle').text.split('-')[0]
            res = res.replace(',', '').strip()
        except Exception:
            res = np.nan
        return res

    def scrape_employee_title(review):
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

    def scrape_review_title(review):
        return review.find_element(by=By.CLASS_NAME, value='reviewLink').text.strip()

    def scrape_review_id(review):
        review_id = review.find_element(by=By.CLASS_NAME, value='reviewLink').get_attribute("href").split('/')[4]
        review_id = review_id.split('-')[-1]
        review_id = review_id[: review_id.find(".htm")]
        return review_id

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

            pro_index = pros.text.find('\nPros')
            con_index = pros.text.find('\nCons')
            res = pros.text[pro_index + 5: con_index].strip()
        except Exception:
            res = np.nan
        return res

    def scrape_cons(review):
        try:
            cons = review.find_element(by=By.CLASS_NAME, value='gdReview')
            expand_show_more(cons)

            con_index = cons.text.find('\nCons')
            continue_index = cons.text.find('\nAdvice to Management')
            if continue_index == -1:
                help_container = review.find_element(by=By.CLASS_NAME,
                                                     value='common__EiReviewDetailsStyle__socialHelpfulcontainer')
                continue_index = cons.text.find(help_container.text)
            res = cons.text[con_index + 5: continue_index].strip()
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
        scrape_review_id,
        scrape_review_date,
        scrape_employee_title,
        scrape_location,

        scrape_review_title,
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
        except Exception:
            return None

        res = {}
        for field in SCHEMA:
            res[field] = scrape(field, review, author)

        assert set(res.keys()) == set(SCHEMA)
        return res

    logger.info(f'Izvlacim recenzije sa strane {page[0]}')

    res = pd.DataFrame([], columns=SCHEMA)
    reviews = browser.find_elements(by=By.CLASS_NAME, value='empReview')
    logger.info(f'Pronadjeno {len(reviews)} recenzija na strani {page[0]}')

    # Osvjezi stranicu ako se nisu ucitale recenzije
    if len(reviews) < 1:
        browser.refresh()
        time.sleep(4)
        reviews = browser.find_elements(by=By.CLASS_NAME, value='empReview')
        logger.info(f'Pronadjeno {len(reviews)} recenzija na strani {page[0]}')
        if len(reviews) < 1:
            valid_page[0] = False  # Ima li ista?

    for review in reviews:
        if not is_featured(review):
            data = extract_review(review)
            if data is not None:
                logger.info(f'Dohvaceni podaci za "{data["review_title"]}" ({data["date"]})')
                res.loc[idx[0]] = data
            else:
                logger.info('Odbacujem blokiranu recenziju')
        else:
            logger.info('Odbacujem izdvojenu recenziju')
        idx[0] = idx[0] + 1

    return res


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
    time.sleep(4)  # Pricekaj jos malko
    page[0] = page[0] + 1


def main(res_df, limit):
    logger.info(f'Scrapeam do {limit} recenzija.')

    page[0] = get_current_page()
    logger.info(f'Pocinjem od strane {page[0]:,}.')
    time.sleep(1)

    reviews_df = extract_from_page()
    res_df = pd.concat([res_df, reviews_df])
    no_revs = 10
    while more_pages() and \
            no_revs < limit and \
            valid_page[0]:
        print(no_revs)
        go_to_next_page()
        try:
            reviews_df = extract_from_page()
            res_df = pd.concat([res_df, reviews_df])
            no_revs += 10
        except Exception:
            break

    return res_df


browser = get_browser()
page = [1]
idx = [0]
valid_page = [True]


def old_main():
    start = time.time()

    sign_in()
    browser.get(url)

    number_of_reviews = \
        browser.find_element(by=By.XPATH, value='//h2[@data-test="overallReviewCount"]').text.split(' ')[4].lower()
    if 'k' in number_of_reviews:
        if '.' in number_of_reviews:
            number_of_reviews = number_of_reviews.replace('k', '00').replace('.', '')
        else:
            number_of_reviews = number_of_reviews.replace('k', '000')
    number_of_reviews = int(number_of_reviews.replace(',', ''))

    limit = min(number_of_reviews, limit)
    limit = math.floor(limit / 3)

    res_df = pd.DataFrame([], columns=SCHEMA)

    # Prvo scrape popularne, zatim sa najmanjom i zatim sa najvecom ocjenom, 1/3 raspodjela
    next_url = url + popular_order_filter
    browser.get(next_url)
    logger.info("SCRAPE POPULAR")
    res_df = main(res_df, limit)

    next_url = url + low_order_filter
    browser.get(next_url)
    logger.info("SCRAPE LOW RATED")
    res_df = main(res_df, limit)

    next_url = url + high_order_filter
    browser.get(next_url)
    logger.info("SCRAPE HIGH RATED")
    res_df = main(res_df, limit)

    logger.info(f'Zapisujem {len(res_df)} recenzija u fajl {filename}')
    res_df.to_csv(filename, index=False, encoding='utf-8')

    end = time.time()
    logger.info(f'Zavrseno za {end - start} sekundi')


def create_final_df():
    # company, review (od _223), polarity (od _15)

    polarity_15_df = pandas.read_csv("reviews_individual_preprocessed_15_polarity.csv", delimiter=",")
    polarity_223_df = pandas.read_csv("reviews_individual_preprocessed_223_polarity.csv", delimiter=",")

    column_polarity_15 = polarity_15_df['polarity'].tolist()  # Extractuj me daddy
    polarity_223_df.drop('polarity', inplace=True, axis=1)  # Obriši me daddy

    polarity_223_df['polarity'] = np.array(column_polarity_15)  # Push me in daddy

    return pandas.DataFrame(data=polarity_223_df).to_csv('on_god_dataset.csv', index=False)


if __name__ == '__main__':
    on_god_dataset = create_final_df()

    print(on_god_dataset)
