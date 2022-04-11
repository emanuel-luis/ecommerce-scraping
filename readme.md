# ecommerce-scrapping
> python: 3.9.6 ou superior

Para rodar este projeto primeiramente deve-se instalar as dependencias do projeto:
```
$ pip install -r requirements.txt
```
O projeto utiliza o **Splash** para integração com JavaScript, então é necessário iniciar o container do docker antes de rodar o `main.py`:
``` 
$ docker run -it -p 8050:8050 scrapinghub/splash --disable-private-mode
```
Por fim, para iniciar a raspagem é só rodar o script principal:

```
$ python main.py
```

## Ferramentas Utilizadas:
- python 3.9.6
- scrapy
- selenium
- scrapy-splash
- docker
- js2py
