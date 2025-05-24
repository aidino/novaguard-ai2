-- Migration script to add project_graph_id columns
-- This adds the ability to store specific CKG identifiers for each scan

BEGIN;

-- Add project_graph_id column to pranalysisrequests table
ALTER TABLE pranalysisrequests 
ADD COLUMN IF NOT EXISTS project_graph_id VARCHAR(255);

-- Add project_graph_id column to fullprojectanalysisrequests table  
ALTER TABLE fullprojectanalysisrequests 
ADD COLUMN IF NOT EXISTS project_graph_id VARCHAR(255);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_pranalysisrequests_project_graph_id 
ON pranalysisrequests(project_graph_id);

CREATE INDEX IF NOT EXISTS idx_fullprojectanalysisrequests_project_graph_id 
ON fullprojectanalysisrequests(project_graph_id);

COMMIT; 