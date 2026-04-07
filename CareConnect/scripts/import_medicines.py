import kagglehub
import pandas as pd
import json
import os
import random

def import_data():
    print("Downloading dataset from Kaggle...")
    # Download latest version
    try:
        path = kagglehub.dataset_download("shudhanshusingh/az-medicine-dataset-of-india")
        print("Path to dataset files:", path)
    except Exception as e:
        print(f"Error downloading dataset: {e}")
        return

    # Find the CSV file
    csv_file = None
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".csv"):
                csv_file = os.path.join(root, file)
                break
        if csv_file:
            break

    if not csv_file:
        print("No CSV file found in the downloaded dataset.")
        return

    print(f"Reading {csv_file}...")
    df = pd.read_csv(csv_file)
    
    # Let's see the columns to map them correctly
    print("Columns found:", df.columns.tolist())
    
    # Expected columns: 'name', 'manufacturer_name', 'price(referral)', 'category', etc.
    # Based on a quick search for this dataset, it might have 'id', 'name', 'price', 'is_rx', etc.
    
    # Mapping logic (adjust based on actual columns found)
    # We want: { id, name, category, price, icon, blurb }
    
    products = []
    
    # Sample categories for mapping
    categories = ['pharmacy', 'devices', 'packages', 'services']
    icons = {
        'pharmacy': '💊',
        'devices': '🩺',
        'packages': '🧰',
        'services': '📹'
    }

    # Clean data: limit to top 100 for demo performance
    sample_size = min(100, len(df))
    df_sample = df.sample(sample_size) if len(df) > 100 else df

    for i, row in df_sample.iterrows():
        # Heuristic mapping
        name = str(row.get('name', 'Unknown Medicine'))
        manufacturer = str(row.get('manufacturer_name', 'Generic'))
        
        # Prices in datasets are often strings or missing
        try:
            p_val = row.get('price(₹)', row.get('price', 0))
            if pd.isna(p_val) or p_val == 0:
                price = random.uniform(5.0, 50.0)
            else:
                price = float(p_val)
        except:
            price = random.uniform(5.0, 50.0)
            
        cat = 'pharmacy' # Most items in this dataset will be pharmacy
        
        products.append({
            'id': f'm{i}',
            'name': name[:50], # Trim long names
            'category': cat,
            'price': round(price, 2),
            'icon': icons[cat],
            'blurb': f"Manufactured by {manufacturer}. Premium verification applied."
        })

    # Add back the original mock items for diversity if needed, or just use the new ones
    
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'data')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'products.json')
    
    with open(output_path, 'w') as f:
        json.dump(products, f, indent=2)
        
    print(f"Successfully exported {len(products)} products to {output_path}")

if __name__ == "__main__":
    import_data()
