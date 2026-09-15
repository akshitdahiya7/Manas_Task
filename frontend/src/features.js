// Mirrors backend/app/features.py for labels and ranges. Kept in sync by
// hand; the backend still validates everything.

export const FEATURE_ORDER = [
  'HighBP', 'HighChol', 'CholCheck', 'BMI', 'Smoker', 'Stroke',
  'HeartDiseaseorAttack', 'PhysActivity', 'Fruits', 'Veggies',
  'HvyAlcoholConsump', 'AnyHealthcare', 'NoDocbcCost', 'GenHlth',
  'MentHlth', 'PhysHlth', 'DiffWalk', 'Sex', 'Age', 'Education', 'Income',
]

// label, min, max, help text
export const FEATURES = {
  HighBP: ['High blood pressure', 0, 1, '0 = no, 1 = yes'],
  HighChol: ['High cholesterol', 0, 1, '0 = no, 1 = yes'],
  CholCheck: ['Cholesterol check in 5 years', 0, 1, '0 = no, 1 = yes'],
  BMI: ['BMI', 12, 98, 'Body mass index'],
  Smoker: ['Smoked 100+ cigarettes', 0, 1, '0 = no, 1 = yes'],
  Stroke: ['Ever had a stroke', 0, 1, '0 = no, 1 = yes'],
  HeartDiseaseorAttack: ['Heart disease or attack', 0, 1, '0 = no, 1 = yes'],
  PhysActivity: ['Physical activity (30 days)', 0, 1, '0 = no, 1 = yes'],
  Fruits: ['Eats fruit daily', 0, 1, '0 = no, 1 = yes'],
  Veggies: ['Eats vegetables daily', 0, 1, '0 = no, 1 = yes'],
  HvyAlcoholConsump: ['Heavy alcohol consumption', 0, 1, '0 = no, 1 = yes'],
  AnyHealthcare: ['Has healthcare coverage', 0, 1, '0 = no, 1 = yes'],
  NoDocbcCost: ['Skipped doctor due to cost', 0, 1, '0 = no, 1 = yes'],
  GenHlth: ['General health', 1, 5, '1 = excellent ... 5 = poor'],
  MentHlth: ['Poor mental health days', 0, 30, 'Days in the last 30'],
  PhysHlth: ['Poor physical health days', 0, 30, 'Days in the last 30'],
  DiffWalk: ['Difficulty walking', 0, 1, '0 = no, 1 = yes'],
  Sex: ['Sex', 0, 1, '0 = female, 1 = male'],
  Age: ['Age band', 1, 13, '1 = 18-24 ... 13 = 80+'],
  Education: ['Education level', 1, 6, '1 = none ... 6 = college graduate'],
  Income: ['Income band', 1, 8, '1 = <$10k ... 8 = >$75k'],
}

// Pre-fills the form so it can be submitted in one click.
export const SAMPLE_RECORD = {
  HighBP: 1, HighChol: 1, CholCheck: 1, BMI: 34, Smoker: 1, Stroke: 0,
  HeartDiseaseorAttack: 0, PhysActivity: 0, Fruits: 0, Veggies: 1,
  HvyAlcoholConsump: 0, AnyHealthcare: 1, NoDocbcCost: 0, GenHlth: 4,
  MentHlth: 10, PhysHlth: 15, DiffWalk: 1, Sex: 1, Age: 10,
  Education: 4, Income: 3,
}
