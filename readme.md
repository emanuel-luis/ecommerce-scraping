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
- python 3.9.6
- scrapy
- selenium
- scrapy-splash
