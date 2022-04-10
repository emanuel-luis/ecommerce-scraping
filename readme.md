# ecommerce-scrapping
Para rodar este projeto primeiramente deve-se instalar as dependencias do projeto:
```
$ pip install -r requirements.txt
```
O projeto utiliza o **Splash** para integração com JavaScript, então é necessário iniciar o container do docker antes de rodar o `main.py`:
``` 
$ docker run -it -p 8050:8050 scrapinghub/splash --disable-private-mode
```

## Ferramentas Utilizadas:
- [scrapy](https://github.com/scrapy/scrapy)
- [selenium](https://github.com/SeleniumHQ/selenium)
- [scrapy-splash](https://github.com/scrapy-plugins/scrapy-splash)
