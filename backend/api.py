from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from Retrieve import process_query
from VectorTools import process_documents, VectorDB
import time
import os
import shutil
from typing import List, Optional
from dotenv import load_dotenv
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import uuid
import uvicorn

# Load environment variables
load_dotenv()
POSTGRESPASS = os.environ.get("POSTGRESPASS")
SECRET_KEY = os.environ.get("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
ADMIN_PASS = os.environ.get("ADMIN_PASS")

# Password hashing for admin login
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Concurrent user tracking
class UserTracker:
    def __init__(self):
        self.active_queries = {}  # {user_id: {start_time, query}}
        self.lock = threading.Lock()
        self.query_counter = 0
    
    def start_query(self, user_id: str, query: str):
        with self.lock:
            self.query_counter += 1
            self.active_queries[user_id] = {
                'start_time': time.time(),
                'query': query,
                'query_number': self.query_counter
            }
            
            active_count = len(self.active_queries)
            
            print(f"\n{'='*50}")
            print(f"🔍 NEW QUERY STARTED")
            print(f"User ID: {user_id}")
            print(f"Query #{self.query_counter}: {query}")
            print(f"Active queries: {active_count}")
            
            if active_count == 1:
                print("✅ PROCESSING: Single user - no waiting")
            elif active_count == 2:
                print("⚠️  CONCURRENT: Two users asking questions!")
                print("🔄 PROCESSING: Both queries simultaneously")
                other_users = [uid for uid in self.active_queries.keys() if uid != user_id]
                for other_user in other_users:
                    other_query = self.active_queries[other_user]
                    elapsed = time.time() - other_query['start_time']
                    print(f"   👥 Other user ({other_user[:8]}...): Query #{other_query['query_number']} running for {elapsed:.2f}s")
            else:
                print(f"🚨 HIGH LOAD: {active_count} users querying simultaneously!")
                print("⚡ PROCESSING: All queries in parallel")
            
            print(f"{'='*50}")
    
    def end_query(self, user_id: str):
        with self.lock:
            if user_id in self.active_queries:
                query_info = self.active_queries[user_id]
                duration = time.time() - query_info['start_time']
                del self.active_queries[user_id]
                
                remaining_count = len(self.active_queries)
                
                print(f"\n{'='*50}")
                print(f"✅ QUERY COMPLETED")
                print(f"User ID: {user_id}")
                print(f"Query #{query_info['query_number']} finished in {duration:.2f}s")
                print(f"Remaining active queries: {remaining_count}")
                
                if remaining_count == 0:
                    print("🎯 ALL CLEAR: No users waiting")
                elif remaining_count == 1:
                    remaining_user = list(self.active_queries.keys())[0]
                    remaining_query = self.active_queries[remaining_user]
                    elapsed = time.time() - remaining_query['start_time']
                    print(f"🔄 CONTINUING: One user still processing (Query #{remaining_query['query_number']}, {elapsed:.2f}s elapsed)")
                else:
                    print(f"🔄 CONTINUING: {remaining_count} users still processing")
                    for remaining_user, remaining_query in self.active_queries.items():
                        elapsed = time.time() - remaining_query['start_time']
                        print(f"   👥 User ({remaining_user[:8]}...): Query #{remaining_query['query_number']}, {elapsed:.2f}s elapsed")
                
                print(f"{'='*50}")
    
    def get_status(self):
        with self.lock:
            return {
                'active_count': len(self.active_queries),
                'active_queries': {
                    user_id: {
                        'query_number': info['query_number'],
                        'elapsed_time': time.time() - info['start_time'],
                        'query': info['query'][:50] + '...' if len(info['query']) > 50 else info['query']
                    }
                    for user_id, info in self.active_queries.items()
                }
            }

# Global user tracker instance
user_tracker = UserTracker()

# User model
class User(BaseModel):
    email: str
    disabled: Optional[bool] = None

class UserInDB(User):
    hashed_password: str

# Replace this with a real database in production
fake_users_db = {
    ADMIN_EMAIL: {
        "email": ADMIN_EMAIL,
        "hashed_password": pwd_context.hash(ADMIN_PASS),
        "disabled": False,
    }
}

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_user(db, email: str):
    if email in db:
        user_dict = db[email]
        return UserInDB(**user_dict)

def authenticate_user(fake_db, email: str, password: str):
    user = get_user(fake_db, email)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = get_user(fake_users_db, email)
    if user is None:
        raise credentials_exception
    return user

# Helper function to clean up temp files
def cleanup_temp_files(file_paths: List[str]):
    """Clean up temporary files"""
    for file_path in file_paths:
        try:
            os.remove(file_path)
        except:
            pass

app = FastAPI()

# Add CORS middleware - this handles OPTIONS requests automatically
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5501",
        "http://127.0.0.1:5500",  
        "https://questionroddixon.com",
        "http://localhost:3000",
        "https://lamoni-rod-wigit.vercel.app",
        "https://freedom-racing.vercel.app",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Authorization"],
    expose_headers=["*"],
)

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(SCRIPT_DIR, "TempDocumentStore")

# Ensure temp directory exists
os.makedirs(TEMP_DIR, exist_ok=True)

class QueryRequest(BaseModel):
    query: str

# Create a thread pool executor for handling concurrent requests
thread_pool = ThreadPoolExecutor(max_workers=10)

@app.get("/")
async def root():
    return {"message": "Welcome to the API"}

@app.get("/status")
async def get_status():
    """Get current status of active queries"""
    status = user_tracker.get_status()
    return status

@app.post("/query/")
async def my_query_endpoint(query: QueryRequest):
    # Generate unique user ID for this request
    user_id = str(uuid.uuid4())
    
    total_start_time = time.time()
    
    # Start tracking this query
    user_tracker.start_query(user_id, query.query)
    
    try:
        # Process the query asynchronously
        process_start_time = time.time()
        
        # Run the query processing in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(thread_pool, lambda: asyncio.run(process_query(query.query)))
        
        process_end_time = time.time()
        process_time = process_end_time - process_start_time
        print(f"TIMING: Query processing total time: {process_time:.4f} seconds")
        
        # Calculate response preparation time
        response_prep_start = time.time()
        # Add timing data to result
        result["api_timing"] = {
            "process_time": f"{process_time:.4f} seconds"
        }
        response_prep_end = time.time()
        print(f"TIMING: Response preparation time: {response_prep_end - response_prep_start:.4f} seconds")
        
        # Calculate total API time
        total_end_time = time.time()
        total_time = total_end_time - total_start_time
        print(f"TIMING: Total API endpoint time: {total_time:.4f} seconds")
        result["api_timing"]["total_time"] = f"{total_time:.4f} seconds"
        
        # Add concurrency info to response
        result["concurrency_info"] = {
            "user_id": user_id,
            "was_concurrent": user_tracker.get_status()['active_count'] > 1
        }
        
        return result
        
    finally:
        # End tracking this query
        user_tracker.end_query(user_id)

@app.post("/query/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/query/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    category: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    upload_start_time = time.time()
    print(f"\n=== INCOMING FILE UPLOAD ===")
    print(f"Category: {category}")
    print(f"Number of files: {len(files)}")
    
    saved_files = []
    
    try:
        # Save uploaded files to temp directory
        for file in files:
            print(f"Processing file: {file.filename}")
            # Validate file extension
            if not file.filename.lower().endswith(('.pdf', '.docx', '.md', '.csv', '.txt')):
                print(f"Skipping invalid file type: {file.filename}")
                continue
                
            file_path = os.path.join(TEMP_DIR, file.filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_files.append(file_path)
            print(f"Saved file: {file.filename}")

        if not saved_files:
            return {"error": "No valid files were uploaded"}

        # Initialize vector DB
        conn_params = {
            "host": "localhost",
            "port": 5432,
            "database": "FreedomRacing",
            "user": "postgres",
            "password": POSTGRESPASS
        }
        vector_db = VectorDB(conn_params)

        # Process documents
        process_start_time = time.time()
        processed_docs = process_documents(TEMP_DIR, category)
        process_end_time = time.time()
        print(f"TIMING: Document processing time: {process_end_time - process_start_time:.4f} seconds")

        # Prepare documents and metadata for vector DB
        documents = []
        metadatas = []
        for doc in processed_docs:
            if hasattr(doc, 'page_content'):
                documents.append(doc.page_content)
            else:
                documents.append(str(doc))
            metadatas.append(doc.metadata)

        # Add to vector DB
        db_start_time = time.time()
        vector_db.add_documents(documents, metadatas)
        db_end_time = time.time()
        print(f"TIMING: Database insertion time: {db_end_time - db_start_time:.4f} seconds")

        upload_end_time = time.time()
        total_time = upload_end_time - upload_start_time
        print(f"TIMING: Total upload processing time: {total_time:.4f} seconds")

        return {
            "message": "Files processed and added to vector database successfully",
            "api_timing": {
                "total_time": f"{total_time:.4f} seconds",
                "processing_time": f"{process_end_time - process_start_time:.4f} seconds",
                "db_insertion_time": f"{db_end_time - db_start_time:.4f} seconds"
            }
        }

    except Exception as e:
        print(f"Error during file upload: {str(e)}")
        return {"error": str(e)}
    
    finally:
        # Clean up temp files (consolidated cleanup)
        cleanup_temp_files(saved_files)

# Add this code to run the server when the file is executed directly
if __name__ == "__main__":
    
    uvicorn.run(app, host="0.0.0.0", port=8001)