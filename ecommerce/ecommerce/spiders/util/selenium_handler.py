from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from importlib import import_module
from selenium.webdriver.remote.webelement import By
from selenium.webdriver.support.wait import WebDriverWait
from scrapy.http import HtmlResponse
from time import sleep as wait

try:
    from ecommerce.src.settings import (SELENIUM_DRIVER_EXECUTABLE_PATH,
                                        SELENIUM_DRIVER_ARGUMENTS,
                                        SELENIUM_DRIVER_NAME)
except ModuleNotFoundError:
    from src.settings import (SELENIUM_DRIVER_EXECUTABLE_PATH,
                              SELENIUM_DRIVER_ARGUMENTS,
                              SELENIUM_DRIVER_NAME)


class SeleniumHandler:
    def __init__(self):
        base_module_path = f'selenium.webdriver.{SELENIUM_DRIVER_NAME}'
        driver_class_module = import_module(f'{base_module_path}.webdriver')
        driver_options_module = import_module(f'{base_module_path}.options')
        driver_service_module = import_module(f'{base_module_path}.service')

        driver_class = getattr(driver_class_module, 'WebDriver')
        driver_options_class = getattr(driver_options_module, 'Options')
        driver_service_class = getattr(driver_service_module, 'Service')

        service = driver_service_class(
            executable_path=SELENIUM_DRIVER_EXECUTABLE_PATH, log_path='nul')
        options = driver_options_class()
        for argument in SELENIUM_DRIVER_ARGUMENTS:
            options.add_argument(argument)

        self.driver = driver_class(options=options, service=service)
        self.waiter = WebDriverWait(self.driver, 10, 0.1)

    def scroll_to(self, x: int, y: int):
        try:
            self.driver.execute_script(f'window.scrollTo({x}, {y})')
        except:
            pass

    @property
    def scroll_height(self):
        return self.driver.execute_script('return document.body.scrollHeight')

    def scroll_to_bottom(self):
        self.scroll_to(0, self.scroll_height)

    def load_page(self, url: str, delay: float):
        driver = self.driver
        driver.get(url)
        wait(2.5)

        old_height = 0
        while True:
            self.scroll_to_bottom()
            wait(delay)
            if old_height == self.scroll_height:
                break
            old_height = self.scroll_height

        return HtmlResponse(
            driver.current_url,
            body=driver.page_source,
            encoding='utf-8'
        )

    def load_on_button(self, url: str, xpath: str, loader=None):
        def click_on_button():
            while element := driver.find_element(*loc):
                self.scroll_to(**element.location)
                element.click()

                if loader:
                    waiter.until_not(
                        EC.visibility_of_element_located(
                            (By.XPATH, loader)
                        )
                    )
                else:
                    wait(2.5)

        driver = self.driver
        waiter = self.waiter

        driver.get(url)
        loc = By.XPATH, xpath

        try:
            click_on_button()
        except NoSuchElementException:
            return HtmlResponse(
                driver.current_url,
                body=driver.page_source,
                encoding='utf-8'
            )

    def quit(self):
        self.driver.quit()
