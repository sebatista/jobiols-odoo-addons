# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

import base64
import zipfile
from io import BytesIO

from odoo import api


@api.model
def _create_module(self, ids):
    mod = self.env['ir.module.record']
    res_xml = mod.generate_xml()
    ids = self.search([('id', 'in', ids)])
    data = ids.read([])[0]
    s = BytesIO()
    zip_file = zipfile.ZipFile(s, 'w')
    dname = data['directory_name']
    data['update_name'] = ''
    data['demo_name'] = ''
    if ['data_kind'] == 'demo':
        data['demo_name'] = '"%(directory_name)s_data.xml"' % data
    else:
        data['update_name'] = '"%(directory_name)s_data.xml"' % data
    depends = self._context.get('depends', {})
    data['depends'] = ','.join(map(lambda x: '"' + x + '"', depends.keys()))
    _manifest = """{
        "name": "%(name)s",
        "version": "%(version)s",
        "author": "%(author)s",
        "website": "%(website)s",
        "category": "%(category)s",
        "description": \"\"\"%(description)s\"\"\",
        "depends": [%(depends)s],
        "data": [%(update_name)s],
        "demo": [%(demo_name)s],
        "installable": True
} """ % data
    filewrite = {
        '__init__.py': '#\n# Generated by Odoo module recorder !\n#\n',
        '__manifest__.py': _manifest,
        data['directory_name'] + '_data.xml': res_xml
    }
    for name, datastr in filewrite.items():
        info = zipfile.ZipInfo(dname + '/' + name)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 2175008768
        if not datastr:
            datastr = ''
        zip_file.writestr(info, datastr)
    zip_file.close()
    return {
        'module_file': base64.encodestring(s.getvalue()),
        'module_filename': data['directory_name'
                                ] + '-' + data['version'] + '.zip',
        'name': data['name'],
        'version': data['version'],
        'author': data['author'],
        'website': data['website'],
        'category': data['category'],
        'description': data['description'],
        'directory_name': data['directory_name'],
    }
