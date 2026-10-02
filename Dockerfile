FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -m study && mkdir /data && chown study:study /data
COPY server.py accounts.py workspace_features.py ./
COPY static ./static
COPY prompts ./prompts
RUN python -c "from pathlib import Path; import re; p=Path('static/style.css'); p.write_text(re.sub(r'url\(\"data:image/jpeg;base64,[^\"]+\"\)', 'none', p.read_text()), encoding='utf-8')" && rm -f static/reference-art.jpg static/art-theme.css
ENV STUDY_DATA_DIR=/data
USER study
EXPOSE 8765
CMD ["python", "server.py", "--multi-user", "--host", "0.0.0.0", "--port", "8765"]
