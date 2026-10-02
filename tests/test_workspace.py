import sys
import json
import unittest
from unittest.mock import patch
import test_app
app=test_app.app
import workspace_features as features

class WorkspaceTests(unittest.TestCase):
    setUp = test_app.StudyTests.setUp
    tearDown = test_app.StudyTests.tearDown
    def test_material_and_task_persistence(self):
        material=features.handle(app,'/api/workspace/save',{'kind':'material','title':'字幕','content':'真实内容'})
        self.assertEqual(features.handle(app,'/api/workspace/list',{'kind':'material'})[0]['content'],'真实内容')
        task=features.handle(app,'/api/workspace/save',{'kind':'task','title':'复习','done':False})
        features.handle(app,'/api/workspace/save',{**task,'done':True})
        self.assertTrue(features.handle(app,'/api/workspace/list',{'kind':'task'})[0]['done'])
        self.assertEqual(features.handle(app,'/api/workspace/list',{'kind':'material'})[0]['id'],material['id'])

    def test_pdf_rejects_fabricated_quote(self):
        data={'pages':[{'page':1,'text':'原文'}]}
        with patch.object(app,'model_call',return_value={'summary':'校对','issues':[{'page':1,'quote':'不存在','suggestion':'修改','reason':'错误'}]}):
            with self.assertRaises(app.AppError):features.handle(app,'/api/pdf/review',data)
        with patch.object(app,'model_call',return_value={'summary':'校对','issues':[{'page':1,'quote':'原文','suggestion':'修改','reason':'表达'}]}):
            self.assertEqual(features.handle(app,'/api/pdf/review',data)['issues'][0]['page'],1)

    def test_invalid_pdf(self):
        with self.assertRaises(app.AppError):features.handle(app,'/api/pdf/extract',{'file':'aGVsbG8='})
