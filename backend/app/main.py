from fastapi import FastAPI

from config import APP_NAME, VERSION


app = FastAPI(title=APP_NAME, version=VERSION)


@app.get("/")
def root():
    return {
        "application": APP_NAME,
        "version": VERSION,
        "message": "Welcome to Me&You.",
    }


def main():
    print("Me&You backend has started.")
    print(f"Application: {APP_NAME}")
    print(f"Version: {VERSION}")


if __name__ == "__main__":
    main()