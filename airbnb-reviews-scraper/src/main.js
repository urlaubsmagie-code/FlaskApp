import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

await Actor.init();

// Get input from the Actor
const input = await Actor.getInput();
const {
    listingUrls = [],
    maxReviewsPerListing = 100,
    proxyConfiguration = { useApifyProxy: true },
} = input;

// Validate input
if (!listingUrls || listingUrls.length === 0) {
    throw new Error('Please provide at least one Airbnb listing URL');
}

// Setup proxy
const proxyConfig = await Actor.createProxyConfiguration(proxyConfiguration);

// Create a PlaywrightCrawler
const crawler = new PlaywrightCrawler({
    proxyConfiguration: proxyConfig,
    maxRequestsPerCrawl: listingUrls.length * 50,
    headless: true,
    
    async requestHandler({ request, page, log, crawler }) {
        log.info(`Processing ${request.url}`);
        
        // Extract listing ID from URL
        const listingId = request.url.match(/\/rooms\/(\d+)/)?.[1];
        
        if (!listingId) {
            log.warning('Could not extract listing ID from URL');
            return;
        }
        
        // Wait for initial page load
        await page.waitForTimeout(2000);
        
        // Handle cookie consent dialog
        try {
            const acceptButton = await page.$('button:has-text("Alle akzeptieren")')
                || await page.$('button:has-text("OK")')
                || await page.$('button:has-text("Accept")');
            
            if (acceptButton) {
                log.info('Accepting cookies...');
                await acceptButton.click();
                await page.waitForTimeout(1000);
            }
        } catch (e) {
            log.info('No cookie dialog found');
        }
        
        // Wait more for content to load
        await page.waitForTimeout(3000);

        // Extract listing basic info
        const listingTitle = await page.$eval('h1', el => el.textContent).catch(() => 'N/A');
        
        // Scroll down to load reviews section
        log.info('Scrolling to reviews section...');
        for (let i = 0; i < 3; i++) {
            await page.evaluate(() => window.scrollBy(0, window.innerHeight));
            await page.waitForTimeout(1000);
        }
        
        // Try to click "Show all reviews" button if it exists
        try {
            const reviewButton = await page.$('button:has-text("Bewertungen")')  
                || await page.$('a[href*="reviews"]')
                || await page.$('button:has-text("reviews")');
            
            if (reviewButton) {
                log.info('Clicking show reviews button...');
                await reviewButton.click();
                await page.waitForTimeout(2000);
            }
        } catch (e) {
            log.info('No reviews button found, continuing...');
        }
        
        // Scroll more to load reviews
        log.info('Loading more reviews...');
        for (let i = 0; i < 3; i++) {
            await page.evaluate(() => window.scrollBy(0, window.innerHeight));
            await page.waitForTimeout(1000);
        }
        
        // Take screenshot for debugging
        await page.screenshot({ path: 'storage/debug_screenshot.png', fullPage: true });
        log.info('Screenshot saved to storage/debug_screenshot.png');
        
        // Debug: Count review elements
        const reviewCount = await page.evaluate(() => {
            return document.querySelectorAll('div[role="listitem"]').length;
        });
        log.info(`Found ${reviewCount} review elements on page`);

        // Extract reviews from the page with multiple selector strategies
        const reviews = await page.evaluate((maxReviews) => {
            // Try multiple selectors for reviews
            let reviewElements = document.querySelectorAll('div[role="listitem"]');
            
            // If no reviews found with role=listitem, try other common patterns
            if (reviewElements.length === 0) {
                reviewElements = document.querySelectorAll('[data-review-id]');
            }
            if (reviewElements.length === 0) {
                // Look for review-like structures
                reviewElements = document.querySelectorAll('div[class*="review"]');
            }
            
            const extractedReviews = [];
            
            for (let i = 0; i < Math.min(reviewElements.length, maxReviews); i++) {
                const reviewEl = reviewElements[i];
                
                // Extract reviewer name - try h2 first (common in newer Airbnb design)
                const nameEl = reviewEl.querySelector('h2') ||
                              reviewEl.querySelector('h3') || 
                              reviewEl.querySelector('span[dir="ltr"]');
                const reviewerName = nameEl ? nameEl.textContent.trim() : '';
                
                // Extract review date with improved logic
                let reviewDate = '';
                
                // Method 1: Look for elements right after the name (common pattern)
                if (nameEl && nameEl.parentElement) {
                    const siblings = Array.from(nameEl.parentElement.parentElement.querySelectorAll('span'));
                    for (const span of siblings) {
                        const text = span.textContent.trim();
                        // Match date patterns (years, months in multiple languages)
                        if (text.match(/\b(20\d{2})\b|month|week|day|monat|woche|tag|vor|ago|january|february|march|april|may|june|july|august|september|october|november|december|januar|februar|märz|mai|juni|juli|oktober|dezember/i)) {
                            if (text.length < 50 && text.length > 3) {
                                reviewDate = text;
                                break;
                            }
                        }
                    }
                }
                
                // Method 2: If still no date, search all spans in review element
                if (!reviewDate) {
                    const allSpans = reviewEl.querySelectorAll('span');
                    for (const span of allSpans) {
                        const text = span.textContent.trim();
                        if (text.match(/^(20\d{2}|\w+\s+20\d{2}|vor\s+\d+|\d+\s+(monat|woche|tag|month|week|day))\w*$/i)) {
                            reviewDate = text;
                            break;
                        }
                    }
                }
                
                // Extract review text - look for longer text content
                let reviewText = '';
                const textSpans = reviewEl.querySelectorAll('span');
                for (const span of textSpans) {
                    const text = span.textContent.trim();
                    // Must be long enough to be a review, and not contain child elements
                    if (text.length > 50 && !span.querySelector('*') && text !== reviewerName) {
                        reviewText = text;
                        break;
                    }
                }
                
                if (reviewerName && reviewText) {
                    extractedReviews.push({
                        reviewerName,
                        reviewDate: reviewDate || 'Date not found',
                        reviewText,
                    });
                }
            }
            
            return extractedReviews;
        }, maxReviewsPerListing);
        
        // Add additional fields to reviews
        const enrichedReviews = reviews.map(review => ({
            listingId,
            listingTitle,
            listingUrl: request.url,
            ...review,
            scrapedAt: new Date().toISOString(),
        }));

        log.info(`Found ${enrichedReviews.length} reviews for listing ${listingId}`);

        // Save reviews to dataset
        if (enrichedReviews.length > 0) {
            await Actor.pushData(enrichedReviews);
        } else {
            log.warning('No reviews found on this page. This could be due to page structure changes or content loading issues.');
            
            // Save debug information
            await Actor.pushData({
                listingId,
                listingTitle,
                listingUrl: request.url,
                error: 'No reviews found',
                debugInfo: 'Page HTML might need inspection',
                scrapedAt: new Date().toISOString(),
            });
        }
    },

    failedRequestHandler({ request, log }) {
        log.error(`Request ${request.url} failed multiple times`);
    },
});

// Prepare initial requests
const initialRequests = listingUrls.map(url => ({
    url: url.trim(),
    uniqueKey: url.trim(),
}));

// Run the crawler
await crawler.run(initialRequests);

console.log('Scraper finished.');
await Actor.exit();
