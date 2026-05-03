# 英文註解: Use the official Python image as a base image
FROM python:3.10-slim

# 英文註解: Set the working directory in the container
WORKDIR /app

# 英文註解: Copy the requirements file into the container
COPY requirements.txt .

# 英文註解: Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 英文註解: Copy the rest of the application code into the container
COPY . .

# 英文註解: Expose the port that the app runs on
EXPOSE 8000

# 英文註解: Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
