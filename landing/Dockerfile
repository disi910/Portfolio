# Start from the official nginx image (Alpine Linux variant = tiny ~5MB)
# This image comes with nginx already installed and configured
FROM nginx:alpine

# Replace the default nginx config with our own
# This tells nginx how to serve our static files
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy our HTML files into nginx's default serving directory
# When someone visits the container, nginx serves files from /usr/share/nginx/html/
COPY index.html /usr/share/nginx/html/
COPY housingclassifier/ /usr/share/nginx/html/housingclassifier/
COPY assets/ /usr/share/nginx/html/assets/
