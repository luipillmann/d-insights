import requests
import pandas as pd
from pandas import Series, DataFrame

import numpy as np
import datetime as dt
from tqdm import tqdm

def get_df_from_query(query, items_per_query='200', total_results_limit=None):
	"""
	Gets items using ML's public API search engine. 
	Uses multiple requests when there are more than 200 results.

	Parameters
	----------
	query : str
			search argument

	items_per_query : str
			how many results per request (max = 200), default '200' 

	total_results_limit : str
			maximum results to be downloaded. If None gets all available, default None

	Returns
	-------
	df : Pandas DataFrame
		DataFrame of all results, without duplicates and following columns:
		['title', 'price', 'sold_quantity', 'available_quantity', 'permalink',
       'thumbnail', 'seller_address', 'seller', 'stop_time', 'revenue'*,
       'start_time'*, 'days_ago'*, 'city'*, 'state'*, 'seller_id'*]	

       * calculated columns (not included in standard API response)
	"""

	results = []
	
	# Initial query to get how many results available
	payload = {'q': str(query), 'limit': str(1), 'offset': str(0)}
	url = 'https://api.mercadolibre.com/sites/MLB/search'
	print('Buscando por "' + query + '"...')
	data = requests.get(url, params=payload).json()
	total_itens = data['paging']['total']  # How many results available

	results = data['results']
	df = DataFrame(results) # Initiatializes main df to be used later in the while loop

	# Simple sanity check for the limit of itens to be requested
	if (total_results_limit == None) or (total_results_limit > total_itens):
	    limit_itens = total_itens
	else:
	    limit_itens = total_results_limit
	    
	# Prints general info about query
	#print(str(total_itens) + ' resultados encontrados no ML.')
	#print(str(limit_itens) + ' itens sendo transferidos. Aguarde...')

	pbar = tqdm(total=limit_itens)  # Initializes progress bar

	# Main loop to make multiple requests to get total results
	offset = 0

	while len(df) < limit_itens:
	    # Calculations or progress bar
	    old_length = len(df)
	    remaining = limit_itens - old_length
	    limit = items_per_query if remaining > items_per_query else remaining+1
	    
	    # Updates query params
	    payload['offset'] = str(offset)
	    payload['limit']  = str(limit)
	    
	    data = requests.get(url, params=payload).json()
	    results = data['results']
	    df_new = DataFrame(results)
	    new_length = len(df_new)
	    
	    # Concatenates new results to df
	    df.reset_index(drop=True)
	    df = pd.concat([df, df_new], axis=0) 
	    
	    # Updates variables for next loop
	    offset = offset + new_length 
	    pbar.update(new_length)

	pbar.close()

	# Selects a subset of columns and fixes index
	df = df[['id', 'title', 'price', 'sold_quantity', 'available_quantity', 'permalink', 'thumbnail', 'seller_address', 'seller', 'stop_time']]
	df = df.set_index('id')	

	# Sorts items by sold quantity and deletes duplicates with less sales (assuming they'd be 0)
	df = df.sort_values(by='sold_quantity', ascending=False)
	df = df.drop_duplicates(subset=['title'], keep='first')

	df['revenue'] = df['sold_quantity'] * df['price']  # Adds revenue column by an operation with sold_quantity and price
	df['stop_time'] = pd.to_datetime(df['stop_time'])  # Fixes 'stop_time' to proper date format

	# Calculates start time and days ago
	start_times = []
	days_ago = []
	today = dt.datetime.today()

	# Iterates over df to calculate 'start_time' subtracting 20 years from \
	# the 'stop_time' (value of 20 is default for ML's data)
	for index, row in df.iterrows():
	    stop_time = df.loc[index, 'stop_time']
	    start = stop_time
	    start = start.replace(year = start.year - 20)
	    ago = (today - start).days
	    days_ago.append(ago)
	    start_times.append(start)

	df['start_time'] = start_times
	df['days_ago'] = days_ago

	# Extracting info from json/dict objects in cells
	cities = [] 
	states = [] 
	sellers =[]

	for index, row in df.iterrows():
	    cities.append(row['seller_address']['city']['name'])    
	    states.append(row['seller_address']['state']['name'])    
	    sellers.append(row['seller']['id'])    

	df['city'] = cities
	df['state'] = states
	df['seller_id'] = sellers

	df = df.sort_index()

	return df

def get_visits_df(main_df, num_items, sort_by='revenue', unit='day', time_ago=365):
	"""
	Gets amount of page visits for certain ML items.

	Parameters
	----------
	main_df : Pandas DataFrame
			df used as data source (format as returned by 'get_df_from_query')

	num_items : str
			how many itens whose visits will be requested (max = 50)

	sort_by : str
			sorts main_df by this parameter, default 'revenue'

	unit : str
			time unit with which to look back ('day' or 'hour'), default 'day'

	time_ago : str
			amount of days or hours, depending on 'unit', default 365

	Returns
	-------
	visits_df : Pandas DataFrame
		DataFrame of all visits to requested items. Index in date format and \
		a column per item with # of visits.
		
	"""
	if num_items > 50:
		num_items = 50
		print('Warning: maximum number of items is 50.')
		print('Resuming with num_items = 50...')

	# Makes comma-separated string from list to use in API multiget
	ids = main_df.sort_values(sort_by, ascending=False).index.values[0:num_items]
	ids_string = ','.join(ids)

	payload = {'ids': ids_string, 'last': time_ago, 'unit': unit}
	url = 'https://api.mercadolibre.com/items/visits/time_window'
	data = requests.get(url, params=payload).json()

	visits_df = DataFrame(data[0]['results']) # initializes a df with the first item
	visits_df = visits_df[['date', 'total']] # gets only main columns
	visits_df.columns = ['date', data[0]['item_id']] # renames 'total' to item's ID

	# Iterates over data items to merge all 'total' columns into same df
	for item in data[1:]:
	    results = item['results']
	    s = DataFrame(results).total
	    s = s.rename(item['item_id'])
	    visits_df = pd.concat([visits_df, s], axis=1)

	# Fixes df, parsing 'date' properly and setting as index column
	visits_df['date'] = pd.to_datetime(visits_df['date'])
	visits_df = visits_df.set_index('date')

	return visits_df

