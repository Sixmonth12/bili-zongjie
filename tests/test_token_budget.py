import unittest
from token_budget import compact_material, output_budget

class BudgetTests(unittest.TestCase):
    def test_summary_preserves_every_source(self):
        segments=[dict(id=f'S{i}',text='内容'+str(i),start='00:01:00',end='00:02:00') for i in range(100)]
        result=compact_material({'segments':segments})
        for s in segments:self.assertIn('['+s['id']+'] '+s['text'],result['segments'])
        self.assertEqual(result['coverage_range']['count'],100)
        self.assertIsInstance(segments,list)

    def test_turn_preserves_refs_bounds_neighbours_and_history(self):
        segments=[dict(id=f'S{i}',text='字'*1000) for i in range(100)]
        data={'segments':segments,'point':{'id':'K1','refs':['S50','S80']},'history':[{'point':'K1','role':'user','text':str(i),'question':'Q'} for i in range(12)],'record':{'status':'需要提示','evidence':['large']},'action':'answer'}
        result=compact_material(data)
        self.assertIn('[S50]',result['segments']);self.assertIn('[S80]',result['segments'])
        self.assertNotIn('[S0]',result['segments']);self.assertEqual(len(result['history']),4)
        self.assertNotIn('evidence',result['record']);self.assertEqual(len(data['history']),12)
        self.assertEqual(output_budget(data),1000)

    def test_long_citation_is_not_cut(self):
        text='字'*9000
        self.assertIn(text,compact_material({'segments':[{'id':'S1','text':text}],'point':{'refs':['S1']}})['segments'])

    def test_question_retrieves_other_source(self):
        segments=[dict(id=f'S{i}',text='无关内容') for i in range(30)]
        segments[25]['text']='编译器将源代码转换'
        result=compact_material({'segments':segments,'point':{'refs':['S1']},'action':'ask','answer':'编译器是什么'})
        self.assertIn('[S25]',result['segments'])
