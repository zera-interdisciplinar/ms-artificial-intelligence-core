# pega a imagem python para usar de base
FROM python:3.12-slim

# define o diretório de trabalho dentro do container
WORKDIR /app

# instala as dependências de sistema exigidas pelo weasyprint para renderizar HTML em PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# copia apenas os arquivos de requisitos do sistema (requirements.txt) para o diretório de trabalho
COPY requirements.txt .

# instala as dependências do sistema
RUN pip install -r requirements.txt

# copia todo o conteúdo do diretório atual para o diretório de trabalho dentro do container (só instala dependencias novamente se houver mudanças no requirements.txt)
COPY . .

# expõe a porta que o FastAPI vai rodar
EXPOSE 8000

# define o comando para rodar a aplicação
CMD ["python", "-m", "app.api.main"]