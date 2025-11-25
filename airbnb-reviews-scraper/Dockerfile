# Use the official Apify SDK image
FROM apify/actor-node:18

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install --production

# Copy source code
COPY . ./

# Run the Actor
CMD npm start
