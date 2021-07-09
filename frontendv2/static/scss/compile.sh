#!/bin/sh
echo "Compiling CSS..."
sass sb-admin-2.scss ../css/sb-admin-2.css 

echo "Minifying CSS..."
curl -X POST -s --data-urlencode 'input@../css/sb-admin-2.css' https://cssminifier.com/raw > ../css/sb-admin-2.min.css

echo "Done."
