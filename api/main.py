from fastapi import FastAPI, UploadFile, File
import uvicorn

app = FastAPI(title="EchoStream API")

@app.get("/")
def read_root():
    return {"message": "EchoStream API is online!"}

@app.post("/upload-video")
async def upload_video(file: UploadFile = File(...)):
    # Aici vom trimite mai târziu video-ul către RabbitMQ
    return {
        "filename": file.filename,
        "status": "Video received. Processing will start soon."
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)