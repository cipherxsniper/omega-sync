#!/usr/bin/env python3
"""
OMEGA MARKETPLACE ENGINE
Token transfers, NFT auctions, bid settlement.
Everything immutably logged to double-entry ledger.
"""

import psycopg2
import json
import uuid
from datetime import datetime, timedelta

PG_LEDGER = "dbname=omega_ledger user=postgres host=127.0.0.1 port=5432"

def transfer_tokens(from_wallet, to_wallet, amount, reason="TRADE"):
    """Transfer OMG tokens. Logs as double-entry to ledger."""
    try:
        conn = psycopg2.connect(PG_LEDGER)
        cur = conn.cursor()
        
        # Check balance
        cur.execute("SELECT balance FROM omega_tokens WHERE wallet_id = %s", (from_wallet,))
        result = cur.fetchone()
        if not result or result[0] < amount:
            return False, "Insufficient balance"
        
        # Execute transfer
        cur.execute("""
            UPDATE omega_tokens SET balance = balance - %s WHERE wallet_id = %s
        """, (amount, from_wallet))
        
        cur.execute("""
            UPDATE omega_tokens SET balance = balance + %s WHERE wallet_id = %s
        """, (amount, to_wallet))
        
        # Log to ledger with UUID id
        entry_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO ledger_entries 
            (id, debit_account, credit_account, amount, memo, event_type, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (entry_id, from_wallet, to_wallet, amount, reason, 'TOKEN_TRANSFER'))
        
        conn.commit()
        cur.close()
        conn.close()
        return True, "Transfer successful"
    except Exception as e:
        return False, str(e)

def list_nft_for_auction(token_id, seller_wallet, starting_price_omg, days=7):
    """List NFT for auction"""
    try:
        conn = psycopg2.connect(PG_LEDGER)
        cur = conn.cursor()
        
        # Check NFT exists
        cur.execute("""
            SELECT token_id FROM nft_registry 
            WHERE token_id = %s AND owner_account_id = %s
        """, (token_id, seller_wallet))
        
        if not cur.fetchone():
            return False, "NFT not found"
        
        # Create listing
        auction_end = datetime.now() + timedelta(days=days)
        cur.execute("""
            INSERT INTO nft_listings (token_id, seller_wallet, starting_price_omg, auction_end)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (token_id, seller_wallet, starting_price_omg, auction_end))
        
        listing_id = cur.fetchone()[0]
        
        # Log to ledger
        entry_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO ledger_entries 
            (id, debit_account, credit_account, amount, memo, event_type, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (entry_id, seller_wallet, 'MARKETPLACE', starting_price_omg, 
              f'NFT #{token_id} listed', 'NFT_LISTED'))
        
        conn.commit()
        cur.close()
        conn.close()
        return True, f"NFT #{token_id} listed (auction #{listing_id})"
    except Exception as e:
        return False, str(e)

def place_bid(listing_id, bidder_wallet, bid_amount):
    """Place bid on NFT auction"""
    try:
        conn = psycopg2.connect(PG_LEDGER)
        cur = conn.cursor()
        
        # Check listing
        cur.execute("""
            SELECT token_id, starting_price_omg, auction_end FROM nft_listings
            WHERE id = %s AND status = 'active'
        """, (listing_id,))
        
        listing = cur.fetchone()
        if not listing:
            return False, "Listing not found"
        
        token_id, starting_price, auction_end = listing
        
        if datetime.now() > auction_end:
            return False, "Auction ended"
        
        if bid_amount < starting_price:
            return False, f"Bid must be >= {starting_price} OMG"
        
        # Check balance
        cur.execute("SELECT balance FROM omega_tokens WHERE wallet_id = %s", (bidder_wallet,))
        result = cur.fetchone()
        if not result or result[0] < bid_amount:
            return False, "Insufficient OMG balance"
        
        # Place bid
        cur.execute("""
            INSERT INTO nft_bids (listing_id, bidder_wallet, bid_amount)
            VALUES (%s, %s, %s)
        """, (listing_id, bidder_wallet, bid_amount))
        
        conn.commit()
        cur.close()
        conn.close()
        return True, f"Bid placed: {bid_amount} OMG"
    except Exception as e:
        return False, str(e)

def settle_auction(listing_id):
    """End auction, transfer NFT and settle payment"""
    try:
        conn = psycopg2.connect(PG_LEDGER)
        cur = conn.cursor()
        
        # Get listing
        cur.execute("""
            SELECT token_id, seller_wallet FROM nft_listings WHERE id = %s
        """, (listing_id,))
        listing = cur.fetchone()
        if not listing:
            return False, "Listing not found"
        
        token_id, seller_wallet = listing
        
        # Get highest bid
        cur.execute("""
            SELECT bidder_wallet, bid_amount FROM nft_bids
            WHERE listing_id = %s
            ORDER BY bid_amount DESC LIMIT 1
        """, (listing_id,))
        
        bid = cur.fetchone()
        if not bid:
            cur.execute("UPDATE nft_listings SET status = 'no_bids' WHERE id = %s", (listing_id,))
            conn.commit()
            return True, "No bids received"
        
        winner_wallet, winning_bid = bid
        
        # Calculate fees (5% to system)
        system_fee = winning_bid * 0.05
        seller_amount = winning_bid * 0.95
        
        # Transfer to seller (95%)
        transfer_tokens(winner_wallet, seller_wallet, seller_amount, "NFT_SALE")
        
        # Transfer fee to system (5%)
        system_wallet = "0b608cb6-6745-4b75-bb9d-fa60e8a1b051"
        transfer_tokens(winner_wallet, system_wallet, system_fee, "MARKETPLACE_FEE")
        
        # Transfer NFT
        cur.execute("""
            UPDATE nft_registry 
            SET owner_account_id = %s, sale_status = 'sold', sold_at = NOW()
            WHERE token_id = %s
        """, (winner_wallet, token_id))
        
        # Mark listing sold
        cur.execute("UPDATE nft_listings SET status = 'sold' WHERE id = %s", (listing_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        return True, f"NFT #{token_id} sold for {winning_bid} OMG"
    except Exception as e:
        return False, str(e)

def get_wallet_balance(wallet_id):
    try:
        conn = psycopg2.connect(PG_LEDGER)
        cur = conn.cursor()
        cur.execute("SELECT balance FROM omega_tokens WHERE wallet_id = %s", (wallet_id,))
        result = cur.fetchone()
        cur.close()
        conn.close()
        return result[0] if result else 0
    except:
        return 0

def get_active_auctions():
    try:
        conn = psycopg2.connect(PG_LEDGER)
        cur = conn.cursor()
        cur.execute("""
            SELECT nl.id, nl.token_id, nl.starting_price_omg,
                   COUNT(nb.id) as bid_count, MAX(nb.bid_amount) as highest_bid
            FROM nft_listings nl
            LEFT JOIN nft_bids nb ON nl.id = nb.listing_id
            WHERE nl.status = 'active' AND nl.auction_end > NOW()
            GROUP BY nl.id, nl.token_id, nl.starting_price_omg
            ORDER BY nl.auction_end ASC
        """)
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        auctions = []
        for row in results:
            auctions.append({
                'listing_id': row[0],
                'token_id': row[1],
                'starting_price': row[2],
                'bid_count': row[3] or 0,
                'highest_bid': row[4]
            })
        return auctions
    except:
        return []

if __name__ == "__main__":
    import sys
    
    if '--test' in sys.argv:
        print("[*] Testing marketplace...\n")
        
        wallet1 = "2109a4cc-a066-4698-a478-a786bf096318"
        wallet2 = "a7889956-ca14-432a-9cb7-7dc17530b7d9"
        
        print(f"Wallet 1: {get_wallet_balance(wallet1)} OMG")
        print(f"Wallet 2: {get_wallet_balance(wallet2)} OMG")
        
        # Transfer test
        print(f"\n[*] Transfer 100 OMG from W1 to W2...")
        success, msg = transfer_tokens(wallet1, wallet2, 100.0, "TEST")
        print(f"    {msg}")
        
        print(f"\nWallet 1 after: {get_wallet_balance(wallet1)} OMG")
        print(f"Wallet 2 after: {get_wallet_balance(wallet2)} OMG")
        
        # Listing test
        print(f"\n[*] List NFT #85 for 500 OMG auction...")
        success, msg = list_nft_for_auction(85, wallet1, 500.0, days=7)
        print(f"    {msg}")
        
        # Bid test
        if success:
            print(f"\n[*] Place bid of 600 OMG from W2...")
            success, msg = place_bid(1, wallet2, 600.0)
            print(f"    {msg}")
        
        # Show auctions
        print(f"\n[*] Active auctions:")
        for auction in get_active_auctions():
            print(f"    Listing #{auction['listing_id']}: NFT #{auction['token_id']} @ {auction['starting_price']} OMG | Bids: {auction['bid_count']} | High: {auction['highest_bid']} OMG")

if '--test-bid' in sys.argv:
    print("[*] Testing bid on active auction...\n")
    
    wallet2 = "a7889956-ca14-432a-9cb7-7dc17530b7d9"
    
    # Get active auctions
    auctions = get_active_auctions()
    if auctions:
        listing = auctions[0]
        listing_id = listing['listing_id']
        print(f"Found auction #{listing_id}: NFT #{listing['token_id']} @ {listing['starting_price']} OMG\n")
        
        print(f"Wallet 2 before bid: {get_wallet_balance(wallet2)} OMG")
        
        print(f"\n[*] Placing bid of 600 OMG...")
        success, msg = place_bid(listing_id, wallet2, 600.0)
        print(f"    {msg}")
        
        print(f"\nWallet 2 after bid: {get_wallet_balance(wallet2)} OMG")
        
        print(f"\n[*] Updated auction:")
        for auction in get_active_auctions():
            if auction['listing_id'] == listing_id:
                print(f"    Listing #{auction['listing_id']}: NFT #{auction['token_id']} | Bids: {auction['bid_count']} | Highest: {auction['highest_bid']} OMG")
    else:
        print("No active auctions found")
