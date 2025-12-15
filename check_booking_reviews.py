import json

# Cargar datos de Booking
with open(r'C:\Users\admin\n8n-docker\files\DatasetScrBooking.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total reviews: {len(data)}\n")
print("=" * 70)

# Mostrar primeras 5 reviews
for i, review in enumerate(data[:10]):
    print(f"\nReview {i+1}:")
    print(f"  Title: {review.get('reviewTitle', 'N/A')}")
    
    liked = review.get('likedText', '')
    if liked:
        print(f"  Liked: {liked[:150]}...")
    else:
        print(f"  Liked: None")
    
    disliked = review.get('dislikedText', '')
    if disliked:
        print(f"  Disliked: {disliked[:100]}...")
    
    print(f"  Language: {review.get('reviewLanguage', 'unknown')}")
    print(f"  Rating: {review.get('rating', 'N/A')}/10")
    print("-" * 70)
