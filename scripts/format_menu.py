import re
import os

menu_path = r'd:\Harsh-GrowwHive\ghub\CareConnect\templates\mega_menu.html'

with open(menu_path, 'r', encoding='utf-8') as f:
    html = f.read()

# We want to replace <a href="#" class="mega-link...">text</a>
# with <a href="{{ url_for('feature_stub', feature_slug='slug') }}" class="mega-link...">text</a>

def repl_link(match):
    before_class = match.group(1)
    text = match.group(2)
    # create slug
    slug = text.lower().replace('&', '').replace(' / ', '-').replace('/', '-').replace(' ', '-').replace(',', '').replace('™', '').replace('+', '').replace('(', '').replace(')', '')
    # clean multiple dashes
    slug = re.sub(r'-+', '-', slug).strip('-')
    
    url_tag = f"{{{{ url_for('feature_stub', feature_slug='{slug}') }}}}"
    return f'<a href="{url_tag}" class="{before_class}">{text}</a>'

# Regex matches class="mega-link..." and the text content
pattern = re.compile(r'<a href="#" class="(mega-link[^"]*)">([^<]+)</a>')
new_html = pattern.sub(repl_link, html)

with open(menu_path, 'w', encoding='utf-8') as f:
    f.write(new_html)

print("Mega menu links successfully updated to use dynamic routing!")
