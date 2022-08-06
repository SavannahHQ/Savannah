#!/bin/sh
echo "Compiling CSS..."
sass sb-admin-2.scss ../css/sb-admin-2.css 

echo "Minifying CSS..."
# curl -X POST -s --data-urlencode 'input@../css/sb-admin-2.css' https://www.toptal.com/developers/cssminifier/api/raw > ../css/sb-admin-2.min.css
echo "Use https://www.cleancss.com/css-minify/ to minify"

echo "Done."
