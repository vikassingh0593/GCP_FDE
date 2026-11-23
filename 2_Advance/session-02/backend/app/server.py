import os
import uvicorn

def main():
    host = "127.0.0.1"
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.api:api", host=host, port=port, reload=True)


if __name__ == "__main__":
    main()
