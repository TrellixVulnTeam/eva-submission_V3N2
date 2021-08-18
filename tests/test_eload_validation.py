import os
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from eva_vcf_merge.detect import MergeType
from eva_vcf_merge.merge import VCFMerger

from eva_submission import ROOT_DIR
from eva_submission.eload_validation import EloadValidation
from eva_submission.submission_config import load_config


class TestEloadValidation(TestCase):
    resources_folder = os.path.join(ROOT_DIR, 'tests', 'resources')

    def setUp(self) -> None:
        config_file = os.path.join(self.resources_folder, 'submission_config.yml')
        load_config(config_file)
        # Need to set the directory so that the relative path set in the config file works from the top directory
        os.chdir(ROOT_DIR)
        self.validation = EloadValidation(2)

    def test_parse_assembly_check_log_failed(self):
        assembly_check_log = os.path.join(self.resources_folder, 'validations', 'failed_assembly_check.log')
        expected = (
            [" The assembly checking could not be completed: Contig '8' not found in assembly report"],
            1,
            0,
            0
        )
        assert self.validation.parse_assembly_check_log(assembly_check_log) == expected

    def test_parse_assembly_check_report_mismatch(self):
        mismatch_assembly_report = os.path.join(self.resources_folder, 'validations', 'mismatch_text_assembly_report.txt')
        expected = (
            [
                "Line 15: Chromosome Chr14, position 7387, reference allele 'T' does not match the reference sequence, expected 'C'",
                "Line 18: Chromosome Chr14, position 8795, reference allele 'A' does not match the reference sequence, expected 'G'",
                "Line 19: Chromosome Chr14, position 8796, reference allele 'C' does not match the reference sequence, expected 'T'",
                "Line 20: Chromosome Chr14, position 9033, reference allele 'G' does not match the reference sequence, expected 'A'",
                "Line 22: Chromosome Chr14, position 9539, reference allele 'C' does not match the reference sequence, expected 'T'",
                "Line 24: Chromosome Chr14, position 9558, reference allele 'C' does not match the reference sequence, expected 'T'",
                "Line 38: Chromosome Chr14, position 10200, reference allele 'A' does not match the reference sequence, expected 'c'",
                "Line 49: Chromosome Chr14, position 10875, reference allele 'G' does not match the reference sequence, expected 'C'",
                "Line 54: Chromosome Chr14, position 11665, reference allele 'A' does not match the reference sequence, expected 'T'",
                "Line 55: Chromosome Chr14, position 11839, reference allele 'G' does not match the reference sequence, expected 'a'"
            ],
            14
        )
        assert self.validation.parse_assembly_check_report(mismatch_assembly_report) == expected

    def test_parse_vcf_check_report(self):
        vcf_check_report = os.path.join(self.resources_folder, 'validations', 'failed_file.vcf.errors.txt')

        valid, error_list, nb_error, nb_warning = self.validation.parse_vcf_check_report(vcf_check_report)
        assert valid is False
        assert len(error_list) == 8
        assert nb_error == 8
        assert nb_warning == 1

    def test_report(self):
        expected_report = '''Validation performed on 2020-11-01 10:37:54.755607
Metadata check: PASS
VCF check: PASS
Assembly check: PASS
Sample names check: PASS
----------------------------------

Metadata check:
  * /path/to/spreadsheet: PASS
    - number of error: 0
    - error messages: 

----------------------------------

VCF check:
  * test.vcf: PASS
    - number of error: 0
    - number of warning: 2
    - first 10 errors: 
    - see report for detail: /path/to/report

----------------------------------

Assembly check:
  * test.vcf: PASS
    - number of error: 0
    - match results: 20/20 (100.0%)
    - first 10 errors: 
    - first 10 mismatches: 
    - see report for detail: /path/to/report

----------------------------------

Sample names check:
  * a1: PASS
    - Samples that appear in the VCF but not in the Metadata sheet: 
    - Samples that appear in the Metadata sheet but not in the VCF file(s): 

----------------------------------

VCF merge:
  * a1: horizontal

----------------------------------
'''
        with patch('builtins.print') as mprint:
            self.validation.report()
        mprint.assert_called_once_with(expected_report)

    def test_detect_and_optionally_merge(self):
        original_content = deepcopy(self.validation.eload_cfg.content)
        analysis_alias = 'alias'
        valid_files = ['file1', 'file2']
        merged_files = {analysis_alias: 'merged.vcf.gz'}
        self.validation.eload_cfg.set('validation', 'valid', 'analyses', analysis_alias, 'vcf_files', value=valid_files)

        with patch('eva_submission.eload_validation.detect_merge_type', return_value=MergeType.HORIZONTAL), \
                patch.object(VCFMerger, 'horizontal_merge', return_value=merged_files):
            # Should detect merge type but not actually merge
            self.validation.detect_and_optionally_merge(False)
            self.assertEqual(
                self.validation.eload_cfg.query('validation', 'merge_type', analysis_alias),
                MergeType.HORIZONTAL.value
            )
            self.assertEqual(
                self.validation.eload_cfg.query('validation', 'valid', 'analyses', analysis_alias, 'vcf_files'),
                valid_files
            )
            # Should perform the merge
            self.validation.detect_and_optionally_merge(True)
            self.assertEqual(
                self.validation.eload_cfg.query('validation', 'valid', 'analyses', analysis_alias, 'vcf_files'),
                ['merged.vcf.gz']
            )
        self.validation.eload_cfg.content = original_content

    def test_merge_multiple_analyses(self):
        original_content = deepcopy(self.validation.eload_cfg.content)
        valid_files = {
            'horizontal': ['h1', 'h2'],
            'vertical': ['v1', 'v2'],
            'neither': ['n1', 'n2']
        }
        detections = [MergeType.HORIZONTAL, MergeType.VERTICAL, None]
        horiz_merged_files = {'horizontal': 'h.vcf.gz'}
        vert_merged_files = {'vertical': 'v.vcf.gz'}
        for analysis_alias, vcf_files in valid_files.items():
            self.validation.eload_cfg.set('validation', 'valid', 'analyses',
                                          analysis_alias, 'vcf_files', value=vcf_files)

        with patch('eva_submission.eload_validation.detect_merge_type', side_effect=detections), \
                patch.object(VCFMerger, 'horizontal_merge', return_value=horiz_merged_files), \
                patch.object(VCFMerger, 'vertical_merge', return_value=vert_merged_files):
            self.validation.detect_and_optionally_merge(True)
            self.assertEqual(
                self.validation.eload_cfg.query('validation', 'valid', 'analyses', 'horizontal', 'vcf_files'),
                ['h.vcf.gz']
            )
            self.assertEqual(
                self.validation.eload_cfg.query('validation', 'valid', 'analyses', 'vertical', 'vcf_files'),
                ['v.vcf.gz']
            )
            self.assertEqual(
                self.validation.eload_cfg.query('validation', 'valid', 'analyses', 'neither', 'vcf_files'),
                ['n1', 'n2']
            )
        self.validation.eload_cfg.content = original_content
