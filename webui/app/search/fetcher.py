from selenium import webdriver
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from bs4 import BeautifulSoup
import requests
import threading
import Queue
import re
import os

class Fetcher(object):
    """Fetching Capability using Selenium"""

    search_driver = None
    screenshot_driver = None
    @staticmethod
    def cleantext(soup):
        for script in soup(["script", "style"]):
            script.extract()  # rip it out
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        text=text.replace('\n',' ')
        return text.encode('utf-8')

    @staticmethod
    def get_selenium_driver(timeout=10, screenshots=False):
        driver = None
        if not screenshots and Fetcher.search_driver is not None:
            driver = Fetcher.search_driver
        elif screenshots and Fetcher.screenshot_driver is not None:
            driver = Fetcher.screenshot_driver

        if driver is not None:
            try:
                driver.get("http://www.example.com/")
                return driver
            except Exception as e:
                print('Selenium driver seems to have crashed, creating a new one {}'.format(str(e)))
                return Fetcher.new_selenium_driver(screenshots)

        else:
            if screenshots:
                Fetcher.screenshot_driver = Fetcher.new_selenium_driver(screenshots)
            else:
                Fetcher.search_driver = Fetcher.new_selenium_driver(screenshots)
            return Fetcher.search_driver

    @staticmethod
    def new_selenium_driver(screenshots, timeout=10):
        if screenshots:
            wd = os.getenv('WEBDRIVER_URL_SCREENSHOTS', "http://sce-chrome-screenshots:3000/webdriver")
        else:
            wd = os.getenv('WEBDRIVER_URL', "http://sce-chrome:3000/webdriver")

        print("WEBDRIVER URL is "+ wd)
        desired_capabilities = DesiredCapabilities.CHROME
        desired_capabilities['chromeOptions'] = {
            "args": ["--disable-extensions","--headless","--no-sandbox"],
            "extensions": []
        }
        driver = webdriver.Remote(command_executor=wd,
                                      desired_capabilities=desired_capabilities)
        driver.implicitly_wait(60)
        driver.set_page_load_timeout(60)
        #driver.set_page_load_timeout(timeout)
        return driver

    @staticmethod
    def close_selenium_driver(driver):
        if driver:
            try:
                driver.close()
                driver.quit()
            except:
                print('An error occurred while closing the driver')

    @staticmethod
    def selenium(url):
        bad_request = False
        driver = Fetcher.new_selenium_driver()
        html = ''
        #text = ''
        title = ''
        try:
            driver.get(url)
        except:
            print('An error occurred while fetching URL: ' + url)
            bad_request = True
        finally:
            try:
                if not bad_request:
                    html = driver.page_source
                    #text = driver.find_element_by_tag_name('body').text
                    title = driver.title
            except:
                print ('An error occurred while fetching URL: ' + url + ' from Selenium')
            finally:
                if driver:
                    Fetcher.close_selenium_driver(driver)
        return [html.encode('utf8')[:20]]

    @staticmethod
    def plain(url):
        #res = urlopen(url)
        html = requests.get(url).content
        #if res.headers.getparam('charset').lower() != 'utf-8':
        #    html = html.encode('utf-8')
        #start = html.find('<title>') + 7  # Add length of <title> tag
        #end = html.find('</title>', start)
        #title = html[start:end]
        soup = BeautifulSoup(html, 'html.parser')
        return [html, soup.title.string.encode('utf-8'), Fetcher.cleantext(soup)]

    @staticmethod
    def read_url(url, queue):
        try:
            #res = urlopen(url)
            #data = res.read()
            data = requests.get(url).content
            print('Fetched %s from %s' % (len(data), url))
            #if res.headers.getparam('charset').lower() != 'utf-8':
            #    data = data.encode('utf-8')
            soup = BeautifulSoup(data, 'html.parser')
            print('Parsed %s from %s' % (len(data), url))
            queue.put([url, data, soup.title.string.encode('utf-8'), Fetcher.cleantext(soup)])
        except Exception as e:
            print(e)
            print('An error occurred while fetching URL: ' + url + ' using urllib. Skipping it!')

    @staticmethod
    def read_url2(url):
        try:
            #res = urlopen(url)
            #data = res.read()
            data = requests.get(url).content
            print('Fetched %s from %s' % (len(data), url))
            #if res.headers.getparam('charset').lower() != 'utf-8':
            #    data = data.encode('utf-8')
            soup = BeautifulSoup(data, 'html.parser')
            print('Parsed %s from %s' % (len(data), url))
            return([url, data, soup.title.string.encode('utf-8'), Fetcher.cleantext(soup)])
        except Exception as e:
            print(e)
            print('An error occurred while fetching URL: ' + url + ' using urllib. Skipping it!')

    @staticmethod
    def is_alive(threads):
        for t in threads:
            if t.isAlive():
                return True
            else:
                threads.remove(t)
        return False

    @staticmethod
    def parallel(urls, top_n):
        result = Queue.Queue()
        threads = [threading.Thread(target=Fetcher.read_url, args=(url, result)) for url in urls]
        for t in threads:
            t.daemon = True
            t.start()
        #for t in threads:
        #    t.join()
        data = []
        while len(data) <= top_n and Fetcher.is_alive(threads):
            data.append(result.get())
        return data

    @staticmethod
    def fetch_multiple(urls, top_n):
        #result = Fetcher.parallel(urls, top_n)
        result = []
        for url in urls:
            result.append(Fetcher.read_url2(url))
        return result

    @staticmethod
    def fetch(url):
        result = ['', '', '']
        try:
            result = Fetcher.plain(url)
        except:
            print('An error occurred while fetching URL: ' + url + ' using urllib. Skipping it!')
            print('An error occurred while fetching URL: ' + url + ' using urllib. Trying Selenium...')
            result = Fetcher.selenium(url)
        return result
