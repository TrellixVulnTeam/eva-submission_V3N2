#!/usr/bin/env nextflow

def helpMessage() {
    log.info"""
    Load variant files into variant warehouse.

    Inputs:
            --valid_vcfs            valid vcfs to load
            --needs_merge           whether horizontal merge is required (false by default)
            --project_accession     project accession
            --load_job_props        job-specific properties, passed as a map
            --eva_pipeline_props    main properties file for eva pipeline
            --project_dir           project directory
            --logs_dir              logs directory
    """
}

params.valid_vcfs = null
params.needs_merge = null
params.project_accession = null
params.load_job_props = null
params.eva_pipeline_props = null
params.project_dir = null
params.logs_dir = null
// executables
params.executable = ["bgzip": "bgzip", "bcftools": "bcftools"]
// java jars
params.jar = ["eva_pipeline": "eva_pipeline"]
// help
params.help = null

// Show help message
if (params.help) exit 0, helpMessage()

// Test inputs
if (!params.valid_vcfs || !params.project_accession || !params.load_job_props || !params.eva_pipeline_props || !params.project_dir || !params.logs_dir) {
    if (!params.valid_vcfs) log.warn('Provide validated vcfs using --valid_vcfs')
    if (!params.project_accession) log.warn('Provide project accession using --project_accession')
    if (!params.load_job_props) log.warn('Provide job-specific properties using --load_job_props')
    if (!params.eva_pipeline_props) log.warn('Provide an EVA Pipeline properties file using --eva_pipeline_props')
    if (!params.project_dir) log.warn('Provide project directory using --project_dir')
    if (!params.logs_dir) log.warn('Provide logs directory using --logs_dir')
    exit 1, helpMessage()
}

// Valid vcfs are redirected to merge step or directly to load
// See https://nextflow-io.github.io/patterns/index.html#_skip_process_execution
(vcfs_to_merge, unmerged_vcfs) = (
    params.needs_merge
    ? [Channel.from(params.valid_vcfs), Channel.empty()]
    : [Channel.empty(), Channel.fromPath(params.valid_vcfs)] )


/*
 * Merge VCFs horizontally, i.e. by sample.
 */
process merge_vcfs {
    input:
    path file_list from vcfs_to_merge.collectFile(name: 'all_files.list', newLine: true)

    output:
    path "${params.project_accession}_merged.vcf.gz" into merged_vcf

    """
    $params.executable.bcftools merge --merge all --file-list $file_list --threads 3 -O z -o ${params.project_accession}_merged.vcf.gz
    """
}


/*
 * Create properties files for load.
 */
process create_properties {
    input:
    // note one of these channels is always empty
    val vcf_file from unmerged_vcfs.mix(merged_vcf)

    output:
    path "load_${vcf_file.getFileName()}.properties" into variant_load_props

    exec:
    props = new Properties()
    params.load_job_props.each { k, v ->
        props.setProperty(k, v.toString())
    }
    props.setProperty("input.vcf", vcf_file.toString())
    // need to explicitly store in workDir so next process can pick it up
    // see https://github.com/nextflow-io/nextflow/issues/942#issuecomment-441536175
    props_file = new File("${task.workDir}/load_${vcf_file.getFileName()}.properties")
    props_file.createNewFile()
    props_file.withWriter { w ->
        props.each { k, v ->
            w.write("$k=$v\n")
        }
    }
    // make a copy for debugging purposes
    new File("${params.project_dir}/load_${vcf_file.getFileName()}.properties") << props_file.asWritable()
}


/*
 * Load into variant db.
 */
process load_vcf {
    clusterOptions "-o $params.logs_dir/pipeline.${variant_load_properties.getFileName()}.log \
                    -e $params.logs_dir/pipeline.${variant_load_properties.getFileName()}.err"

    input:
    path variant_load_properties from variant_load_props

    memory '5 GB'

    """
    java -Xmx4G -jar $params.jar.eva_pipeline --spring.config.location=file:$params.eva_pipeline_props --parameters.path=$variant_load_properties
    """
}
