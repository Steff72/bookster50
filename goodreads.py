import requests
res = requests.get("https://www.goodreads.com/book/review_counts.json",
                   params={"key": "gvlQ3F8KG7Z3kr89nAQiw", "isbns": "9781632168146"})
print(res.json())
