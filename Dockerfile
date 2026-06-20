FROM python:3.10-slim

# Install system dependencies, including ffmpeg if needed (though static_ffmpeg is used, it's good to have standard libraries)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Set up a new user named "user" with user ID 1000
RUN useradd -m -u 1000 user

# Switch to the "user" user
USER user

# Set home to the user's home directory
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PORT=7860

# Set the working directory to the user's home directory
WORKDIR $HOME/app

# Copy the current directory contents into the container at $HOME/app setting the owner to the user
COPY --chown=user . $HOME/app

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create necessary directories and ensure proper permissions
RUN mkdir -p downloads templates static/css static/js bin && \
    chmod -R 777 $HOME/app

# Expose port 7860 for Hugging Face Spaces
EXPOSE 7860

# Run the bot and web app
CMD ["python", "bot.py"]
