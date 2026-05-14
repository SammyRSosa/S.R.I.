import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

def test_groq():
    key = os.getenv("GROQ_API_KEY")
    print(f"Testing with key: {key[:10]}...")
    client = Groq(api_key=key)
    try:
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": "Say 'Groq is ready!'"}],
            model="llama-3.3-70b-versatile",
        )

        print("Response:", completion.choices[0].message.content)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_groq()
