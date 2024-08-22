import json
import os.path
import requests
from collections import OrderedDict
import pandas as pd
from sys import argv, exit
import re

# Flags, accumulators
interactiveMode = False
collector = []

# create folders if they don't exist
if not os.path.exists('jsons'):
    os.makedirs('jsons')

##############################
# Functions:
def downloadFile(x,y):
    if os.path.exists(y):
        return
    print('\nDownloading '+x)

    try:
        r = requests.get(x, allow_redirects=True)
    except requests.exceptions.RequestException as e:
        print('\nInvalid URL.')
        if interactiveMode: interactiveExit()
        else: exit()

    with open(y, 'wb') as f:
        f.write(r.content)
    print('Saved as '+ y)

def interactiveExit():
    print('\n\nPress any key to exit.\n')
    a = input()
    exit()

def extract_subscription_details(description):
    subscription_pattern = r'Subscribe & Save (\d+)%'
    match = re.search(subscription_pattern, description)
    if match:
        discount = match.group(1)
        return True, int(discount)
    return False, 0

def process_attributes(product):
    attributes = []
    for i, option in enumerate(product.get('options', []), 1):
        attribute = {
            f'Attribute {i} name': option.get('name'),
            f'Attribute {i} value(s)': ', '.join(option.get('values', [])),  # Changed from '|' to ', '
            f'Attribute {i} visible': 1,
            f'Attribute {i} global': 1
        }
        attributes.append(attribute)
    return attributes

#############################
# Main Program Start:

# taking first argument as URL, or asking user to provide URL
if len(argv) > 1:
    shopifyURL = argv[1]
else:
    print('\n\nEnter a shopify URL, like https://your-shopify-store.com:')
    shopifyURL = input()
    interactiveMode = True

downloadFile(shopifyURL + '/collections.json', 'jsons/collections.json')

collections = json.load(open('jsons/collections.json')).get('collections', [])

#########################################
# Looping through each collection

print('\n\nShopify API to WooCommerce-import-CSV converter.\n\nStarting to loop through collections')
for collection in collections:
    handle = collection.get('handle')
    category = collection.get('title')

    countCheck = collection.get('products_count')
    productJsonURL = f'{shopifyURL}/collections/{handle}/products.json'
    productJson = f'jsons/{handle}.json'
    
    if countCheck: downloadFile(productJsonURL, productJson)
    else: continue

    products = json.load(open(productJson)).get('products', [])

    print(f'\nCATEGORY: {category} has {len(products)} products.')

    #########################################
    # Looping through each product entry in the collection
    for product in products:
        common = OrderedDict()
        numVariants = len(product.get('variants', []))

        common['SKU'] = product.get('handle')

        #########################################
        # duplicates check, and if so, then just add the collection to categories and skip to next loop.
        repeatingSKU = False
        for x in collector:
            if x['SKU'] == common['SKU']:
                x['Categories'] += f', {category}'
                categorycount = len(x['Categories'].split(', '))
                print(f"handle={x['SKU']} encountered again, it now has {categorycount} Categories.")
                repeatingSKU = True
                break
        if repeatingSKU:
            continue

        common['Name'] = product.get('title')
        common['Description'] = product.get('body_html', '').replace('\n', '')
        common['Categories'] = category
        common['Tags'] = ', '.join(product.get('tags', []))
        # Images:
        imageURLs = [x.get('src') for x in product.get('images', [])]
        common['Images'] = ', '.join(imageURLs)

        # Subscription details
        is_subscription, discount = extract_subscription_details(common['Description'])
        common['Subscriptions Enabled'] = 1 if is_subscription else 0
        common['Subscription Discount'] = discount if is_subscription else ''

        # Attributes
        attributes = process_attributes(product)
        for attr in attributes:
            common.update(attr)

        # assumptions
        common['Is featured?'] = 0
        common['Stock'] = ''
        common['Backorders allowed?'] = 0
        common['Sold individually?'] = 0
        common['Length (in)'] = ''
        common['Width (in)'] = ''
        common['Height (in)'] = ''
        common['Allow customer reviews?'] = 0

        # defaults
        common['Published'] = 1
        common['Visibility in catalog'] = 'visible'

        if numVariants < 2:
            # Simple product
            row = OrderedDict(common)
            row['Type'] = 'simple'
            variant = product['variants'][0]
            row['Regular price'] = variant.get('price')
            row['In stock?'] = 1 if variant.get('available') else 0
            collector.append(row)
        else:
            # Variable product
            row = OrderedDict(common)
            row['Type'] = 'variable'
            collector.append(row)

            # Handle variations
            for variant in product.get('variants', []):
                row2 = OrderedDict(common)
                row2['Type'] = 'variation'
                row2['Parent'] = common['SKU']
                row2['SKU'] = f"{common['SKU']}-{variant.get('id')}"
                row2['Name'] = f"{common['Name']} - {' '.join(variant.get('title').split(' / '))}"
                row2['Regular price'] = variant.get('price')
                row2['In stock?'] = 1 if variant.get('available') else 0

                # Set attribute values for this variation
                for i, option in enumerate(product.get('options', []), 1):
                    attribute_name = option.get('name')
                    attribute_value = variant.get(f'option{i}')
                    row2[f'Attribute {i} name'] = attribute_name
                    row2[f'Attribute {i} value(s)'] = attribute_value

                if variant.get('featured_image'):
                    featured = variant['featured_image'].get('src')
                    if featured in imageURLs:
                        imageURLs.remove(featured)
                    imageURLs.insert(0, featured)
                    row2['Images'] = ', '.join(imageURLs)

                collector.append(row2)

df = pd.DataFrame(collector)
df.to_csv('woocommerce-import.csv', index=False)

print(f'\n\nProcessed {shopifyURL}. Total {len(df)} products found.')
print('Created woocommerce-import.csv in the same folder where you ran this script.')

if interactiveMode:
    interactiveExit()